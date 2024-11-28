#!/usr/bin/env python

# Copyright 2021-2024 Citrix Systems, Inc.  All rights reserved.
# Use of this software is governed by the license terms, if any,
# which accompany or are included with this software.

"""
Checks whether config file contains invalid
epressions and features.

Dependency packages: PLY, pytest
"""

# Ensure that the version string conforms to PEP 440:
# https://www.python.org/dev/peps/pep-0440/
__version__ = "1.1"

import re
import argparse
import glob
import importlib
import logging
import logging.handlers
import os
import os.path
import sys
from inspect import cleandoc
import inspect

import cli_yacc
import nspepi_common as common

import check_classic_configs

# Log handlers that need to be saved from call to call
file_log_handler = None
console_log_handler = None


def setup_logging(log_file_name, file_log_level):
    """
    Sets up logging for the program.

    Args:
        log_file_name: The name of the log file
        file_log_level: The level of logs to put in the file log
    """
    global file_log_handler
    global console_log_handler
    # create logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    # if called multiple times, remove existing handlers
    logger.removeHandler(file_log_handler)
    logger.removeHandler(console_log_handler)
    # create file handler and roll logs if needed
    exists = os.path.isfile(log_file_name)
    file_log_handler = logging.handlers.RotatingFileHandler(log_file_name,
                                                            mode='a',
                                                            backupCount=9)
    if exists:
        file_log_handler.doRollover()
    # set the file log handler level
    file_log_handler.setLevel(file_log_level)
    # create console handler that sees even info messages
    console_log_handler = logging.StreamHandler()
    console_log_handler.setLevel(logging.INFO)
    # create formatters and add them to the handlers
    fh_format = logging.Formatter('%(message)s')
    file_log_handler.setFormatter(fh_format)
    # add the handlers to the logger
    logger.addHandler(file_log_handler)


def output_line(line, outfile, verbose):
    """
    Output a (potentially) converted line.

    Args:
        line: the line to output
        outfile: Output file to write converted commands
        verbose: True iff converted commands should also be output to console
    """
    outfile.write(line)
    if verbose:
        logging.info(line.rstrip())


def check_config_file(infile, outfile, verbose):
    """
    Process ns config file passed in argument and report the classic and
    removed commands.

    Args:
        infile: NS config file to be converted
        outfile: Output file to write commands using removed config
        verbose: True iff converted commands should also be output to console
    """
    cli_yacc.cli_yacc_init()
    # Register handler methods for various commands
    currentfile = os.path.abspath(inspect.getfile(inspect.currentframe()))
    currentdir = os.path.dirname(currentfile)
    for module in glob.glob(os.path.join(currentdir, 'check_classic_configs.py')):
        importlib.import_module(os.path.splitext(os.path.basename(module))[0])
    # call methods registered to be called before the start of processing
    # config file.
    for m in common.init_methods:
        m.method(m.obj)
    lineno = 0
    for cmd in infile:
        lineno += 1
        parsed_tree = cli_yacc.cli_yacc_parse(cmd, lineno)
        if parsed_tree is not None:
            # construct dictionary key to look up registered method to call to
            # parse and transform the command to be emitted
            # Registered method can return either string or tree.
            key = " ".join(parsed_tree.get_command_type()).lower()
            if key in common.dispatchtable:
                for m in common.dispatchtable[key]:
                    # Since, we are only checking the config and not
                    # converting to advanced, so list will contains
                    # at most only one command.
                    output = m.method(m.obj, parsed_tree)
                    if len(output) != 0:
                         output_line(cmd, outfile, verbose)



def main():
    desc = cleandoc(
        """
        Checks whether invalid config is present in input file
        """)
    arg_parser = argparse.ArgumentParser(
        prog="configCheck",
        description=desc,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    arg_parser.add_argument(
        "-f", "--infile", metavar="<path to ns config file>",
        help="Checks whether invalid config is present in the input file",
        required=True)
    arg_parser.add_argument(
        "-v", "--verbose", action="store_true", help="show verbose output")
    arg_parser.add_argument(
        '-V', '--version', action='version',
        version='%(prog)s {}'.format(__version__))
    arg_parser.add_argument(
        '-B', '--buildVersion', default='13.1',
        help="Build version for which invalid commands"
	" need to check")
    try:
        args = arg_parser.parse_args()
    except IOError as e:
        exit(str(e))
    # obtain logging parameters and setup logging
    conf_file_path = os.path.dirname(args.infile)
    conf_file_name = os.path.basename(args.infile)
    check_classic_configs.check_configs_init()
    check_classic_configs.build_version = args.buildVersion
    new_path = os.path.join(conf_file_path, "issues_" + conf_file_name)
    with open(args.infile, 'r') as infile:
        with open(new_path, 'w') as outfile:
            check_config_file(infile, outfile, args.verbose)


if __name__ == '__main__':
    main()
