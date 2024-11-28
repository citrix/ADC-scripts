#!/usr/bin/env python

# Copyright 2021-2024 Citrix Systems, Inc. All rights reserved.
# Use of this software is governed by the license terms, if any,
# which accompany or are included with this software.

import copy

import cli_lex
import nspepi_common as common
import check_classic_expr
from nspepi_parse_tree import *


def check_configs_init():
    """Initialize global variables uses by this module"""
    global policy_entities_names
    global classic_entities_names
    global named_expr
    global build_version
    named_expr = {}
    policy_entities_names = set()
    classic_entities_names = set()
    # Register built-in named expressions.
    NamedExpression.register_built_in_named_exprs()
    build_version = "13.1"


def is_advanced_removed_expr_present(expr):
    """
    Checks for the advanced expressions, Q and S prefixes,
    HTTP.REQ.BODY and SYS.EVAL_CLASSIC_EXPR, which are removed.
    Args:
	expr: Expression or command on which removed expressions
              need to check.
    Returns True if the removed expressions are present, otherwise
    False.
    """
    if re.search(r'\bSYS\s*\.\s*EVAL_CLASSIC_EXPR\s*\(',
                 expr, re.IGNORECASE):
        return True

    body_expr = re.compile(r'\bHTTP\s*\.\s*REQ\s*\.\s*BODY\b\s*', re.IGNORECASE)
    expr_len = len(expr)
    for match in re.finditer(body_expr, expr):
        start_index = match.start()
        length = match.end() - match.start()
        if (((start_index + length) >= expr_len) or
             (expr[start_index + length] != '(')):
            return True

    if re.search(r'\b((Q\.HOSTNAME)|(Q\.TRACKING)|'
                 '(Q\.METHOD)|(Q\.URL)|(Q\.VERSION)|'
                 '(Q\.CONTENT_LENGTH)|(Q\.HEADER)|'
                 '(Q\.IS_VALID)|(Q\.DATE)|'
                 '(Q\.COOKIE)|(Q\.BODY)|(Q\.TXID)|'
                 '(Q\.CACHE_CONTROL)|(Q\.USER)|'
                 '(Q\.IS_NTLM_OR_NEGOTIATE)|'
                 '(Q\.FULL_HEADER)|'
                 '(Q\.LB_VSERVER)|(Q\.CS_VSERVER))',
                 expr, re.IGNORECASE):
        return True

    if re.search(r'\b((S\.VERSION)|(S\.STATUS)|'
                  '(S\.STATUS_MSG)|(S\.IS_REDIRECT)|'
                  '(S\.IS_INFORMATIONAL)|(S\.IS_SUCCESSFUL)|'
                  '(S\.IS_CLIENT_ERROR)|(S\.IS_SERVER_ERROR)|'
                  '(S\.TRACKING)|(S\.HEADER)|(S\.FULL_HEADER)|'
                  '(S\.IS_VALID)|(S\.DATE)|(S\.BODY)|'
                  '(S\.SET_COOKIE)|(S\.SET_COOKIE2)|'
                  '(S\.CONTENT_LENGTH)|'
                  '(S\.CACHE_CONTROL)|(S\.TXID)|(S\.MEDIA))',
		  expr, re.IGNORECASE):
        return True
    return False


def remove_quotes(val):
    """
        Helper function to remove the surrounding
        quotes from a CLI parameter.
        val - CLI parameter that needs quotes removed.
        Returns the dequoted CLI parameter
    """
    result = val
    if val.startswith('"') or val.startswith("'"):
        lexer = cli_lex.Lexer()
        lexer.input(val)
        token = lexer.token()
        assert token.type == "NON_KEY"
        result = token.value
    return result


def is_classic_named_expr_present(expr):
    """
        Helper function to check that
        classic expression names present in the
        given expression or not.
        expr - Expression in which classic
           expression names need to be found.
        Returns True if classic named expression is present,
        otherwise returns False.
    """
    lexer = cli_lex.Lexer()
    lexer.input(expr)
    classic_expr_info_list = []
    while True:
        next_token = lexer.adv_expr_token()
        if not next_token:
            break
        token_value = str(next_token)
        if token_value in NamedExpression.built_in_named_expr:
            return True
        elif token_value in classic_entities_names:
            return True
    return False

class CheckConfig(object):
    """Base class to check the config"""

    @staticmethod
    def check_pos_expr(commandParseTree, pos, check_removed_expr = True):
        """
            Check the expression present at a given position
            commandParseTree - the parse tree to modify
            pos - the position of the parameter to modify
            check_removed_expr - True iff advanced expressions
                which are removed need to check.
            If the expression is classic, then invalid
            flag would be set.
        """
        rule_node = commandParseTree.positional_value(pos)
        rule_expr = rule_node.value
        converted_expr = check_classic_expr.check_classic_expr(rule_expr)
        if converted_expr is None:
            logging.error('Error in checking command : ' +
                          str(commandParseTree))
        elif converted_expr == "Invalid Expression":
            commandParseTree.set_invalid()
        else:
            # converted_expr will have quotes and rule_expr will not have
            # quotes. Since we are comparing these 2 expressions, removing
            # quotes from converted_expr.
            converted_expr = remove_quotes(converted_expr)
            if converted_expr != rule_expr:
                # expression is converted, this is classic.
                commandParseTree.set_invalid()
            elif is_classic_named_expr_present(converted_expr):
                commandParseTree.set_invalid()
            elif check_removed_expr:
                CheckConfig.check_adv_expr_list(commandParseTree, [pos])
        return commandParseTree

    @staticmethod
    def check_keyword_expr(commandParseTree, keywordName):
        """
            Check the expression present as a value of
            the given keyword name.
            commandParseTree - the parse tree to modify
            keywordName - the name of the keyword parameter to modify
            If the expression is classic, then invalid
            flag would be set.
        """
        if not commandParseTree.keyword_exists(keywordName):
            return commandParseTree
        rule_node = commandParseTree.keyword_value(keywordName)
        rule_expr = rule_node[0].value
        converted_expr = check_classic_expr.check_classic_expr(rule_expr)
        if converted_expr is None:
            logging.error('Error in checking command : ' +
                          str(commandParseTree))
        elif converted_expr == "Invalid Expression":
                commandParseTree.set_invalid()
        else:
            # converted_expr will have quotes and rule_expr will not have
            # quotes. Since we are comparing these 2 expressions, removing
            # quotes from converted_expr.
            converted_expr = remove_quotes(converted_expr)
            if converted_expr != rule_expr:
                # expression is converted, this is classic.
                commandParseTree.set_invalid()
            elif is_classic_named_expr_present(converted_expr):
                commandParseTree.set_invalid()
            else:
                CheckConfig.check_adv_expr_list(commandParseTree, [keywordName])
        return commandParseTree

    @staticmethod
    def register_policy_entity_name(commandParseTree):
        """ Add the entity name in the global list."""
        name = commandParseTree.positional_value(0).value.lower()
        policy_entities_names.add(name)

    @staticmethod
    def register_classic_entity_name(commandParseTree):
        """ Add the classic entity name in the classic global list."""
        name = commandParseTree.positional_value(0).value.lower()
        classic_entities_names.add(name)

    @staticmethod
    def check_adv_expr_list(commandParseTree, param_list):
        """
        Checks that if any advanced expression which have
        been removed are present in any of the parameters
        provided by param_list.
        Args:
            commandParseTree: The parse tree to check
            param_list: List of the parameters which need to check
                        for the advanced removed expression.
        """
        for param in param_list:
            adv_expr = common.get_cmd_arg(param, commandParseTree)
            if adv_expr is None:
                continue
            if is_advanced_removed_expr_present(adv_expr):
                commandParseTree.set_invalid()
                break


@common.register_class_methods
class CacheRedirection(CheckConfig):
    """ Handle CR feature """

    # Classic built-in policy names
    built_in_policies = [
        "bypass-non-get",
        "bypass-cache-control",
        "bypass-dynamic-url",
        "bypass-urltokens",
        "bypass-cookie"
    ]

    built_in_policies_adv = {
        "bypass-non-get-adv",
        "bypass-cache-control-adv",
        "bypass-dynamic-url-adv",
        "bypass-urltokens-adv",
        "bypass-cookie-adv"
    }


    @common.register_for_cmd("add", "cr", "policy")
    def check_policy(self, commandParseTree):
        """
        Checks classic CR policy.
        """
        policy_name = commandParseTree.positional_value(0).value
        lower_policy_name = policy_name.lower()

        #Ignore default classic policies
        if lower_policy_name in self.built_in_policies:
            return []

        pol_obj = common.Policy(policy_name, self.__class__.__name__)

        #Ignore default advanced policies
        if lower_policy_name in self.built_in_policies_adv:
            pol_obj.policy_type = "advanced"
            return []

        common.pols_binds.store_policy(pol_obj)
        """
        If action field is not set, then it is classic policy,
        else it is an advanced policy.
        """
        if commandParseTree.keyword_exists('action'):
            CacheRedirection.check_adv_expr_list(commandParseTree, ["rule"])
            if commandParseTree.invalid:
                return [commandParseTree]
            return []
        else:
            commandParseTree.set_invalid()
            return [commandParseTree]

    @common.register_for_cmd("bind", "cr", "vserver")
    def check_cr_vserver_bind(self, bind_parse_tree):
        """
        Handles CR vserver bind command.
        bind cr vserver <name> -policyName <string>
        -priority <positive_integer> -gotoPriorityExpression <expression>
        """
        if not bind_parse_tree.keyword_exists('policyName'):
            return []

        policy_name = bind_parse_tree.keyword_value("policyName")[0].value
        class_name = self.__class__.__name__
        policy_type = common.pols_binds.get_policy(policy_name).module
        # When policy is CR policy.
        if policy_type == class_name:
            # check for classic built-in policy.
            if policy_name in self.built_in_policies:
                bind_parse_tree.set_invalid()
                return [bind_parse_tree]

        return []


@common.register_class_methods
class SSL(CheckConfig):
    """ Handle SSL feature """

    @common.register_for_cmd("add", "ssl", "policy")
    def check_policy(self, commandParseTree):
        """
        Check classic SSL policy.
        """

        commandParseTree = SSL.check_keyword_expr(commandParseTree, 'rule')
        if commandParseTree.invalid:
            return [commandParseTree]
        return []


@common.register_class_methods
class APPFw(CheckConfig):
    """ Handle APPFw feature """

    @common.register_for_cmd("add", "appfw", "policy")
    def check_policy(self, commandParseTree):
        """
        Check classic AppFw policy
        """
        commandParseTree = APPFw.check_pos_expr(commandParseTree, 1)
        if commandParseTree.invalid:
            return [commandParseTree]
        return []


@common.register_class_methods
class Patset(CheckConfig):
    """ Patset entity """

    @common.register_for_cmd("add", "policy", "patset")
    def register_name(self, commandParseTree):
        Patset.register_policy_entity_name(commandParseTree)
        if commandParseTree.keyword_exists('indexType'):
            commandParseTree.set_invalid()
            return [commandParseTree]
        return []


@common.register_class_methods
class Dataset(CheckConfig):
    """ Dataset entity """

    @common.register_for_cmd("add", "policy", "dataset")
    def register_name(self, commandParseTree):
        Dataset.register_policy_entity_name(commandParseTree)
        if commandParseTree.keyword_exists('indexType'):
            commandParseTree.set_invalid()
            return [commandParseTree]
        return []


@common.register_class_methods
class Patclass(CheckConfig):
    """ Patclass entity """

    @common.register_for_cmd("add", "policy", "patclass")
    def check_add_patclass(self, commandParseTree):
        Patclass.register_policy_entity_name(commandParseTree)
        commandParseTree.set_invalid()
        return [commandParseTree]

    @common.register_for_cmd("bind", "policy", "patclass")
    def check_bind_patclass(self, commandParseTree):
        Patclass.register_policy_entity_name(commandParseTree)
        commandParseTree.set_invalid()
        return [commandParseTree]


@common.register_class_methods
class HTTP_CALLOUT(CheckConfig):
    """ HTTP callout entity """

    @common.register_for_cmd("add", "policy", "httpCallout")
    def register_name(self, commandParseTree):
        HTTP_CALLOUT.register_policy_entity_name(commandParseTree)
        HTTP_CALLOUT.check_adv_expr_list(
                commandParseTree, ["hostExpr", "urlStemExpr", "headers",
                "parameters", "bodyExpr", "fullReqExpr", "resultExpr"])
        if commandParseTree.invalid:
            return [commandParseTree]
        return []


@common.register_class_methods
class StringMap(CheckConfig):
    """ String map entity """

    @common.register_for_cmd("add", "policy", "stringmap")
    def register_name(self, commandParseTree):
        StringMap.register_policy_entity_name(commandParseTree)
        return []


@common.register_class_methods
class NSVariable(CheckConfig):
    """ NS Variable entity """

    @common.register_for_cmd("add", "ns", "variable")
    def register_name(self, commandParseTree):
        NSVariable.register_policy_entity_name(commandParseTree)
        return []


@common.register_class_methods
class EncryptionKey(CheckConfig):
    """ Encryption key entity """

    @common.register_for_cmd("add", "ns", "encryptionKey")
    def register_name(self, commandParseTree):
        EncryptionKey.register_policy_entity_name(commandParseTree)
        return []


@common.register_class_methods
class HMACKey(CheckConfig):
    """ HMAC key entity """

    @common.register_for_cmd("add", "ns", "hmacKey")
    def register_name(self, commandParseTree):
        HMACKey.register_policy_entity_name(commandParseTree)
        return []


@common.register_class_methods
class NamedExpression(CheckConfig):
    """ Handle Named expression feature """

    # Built-in classic named expression names
    built_in_named_expr = {
        "ns_true",
        "ns_false",
        "ns_non_get",
        "ns_cachecontrol_nostore",
        "ns_cachecontrol_nocache",
        "ns_header_pragma",
        "ns_header_cookie",
        "ns_ext_cgi",
        "ns_ext_asp",
        "ns_ext_exe",
        "ns_ext_cfm",
        "ns_ext_ex",
        "ns_ext_shtml",
        "ns_ext_htx",
        "ns_url_path_cgibin",
        "ns_url_path_exec",
        "ns_url_path_bin",
        "ns_url_tokens",
        "ns_ext_not_gif",
        "ns_ext_not_jpeg",
        "ns_cmpclient",
        "ns_slowclient",
        "ns_content_type",
        "ns_msword",
        "ns_msexcel",
        "ns_msppt",
        "ns_css",
        "ns_xmldata",
        "ns_mozilla_47",
        "ns_msie"
    }

    # List of the builtin named expressions
    built_in_named_expr_list = [
            "is_vpn_url",
            "is_aoservice",
            "ns_non_get",
            "ns_non_get_adv",
            "ns_cachecontrol_nostore",
            "ns_cachecontrol_nostore_adv",
            "ns_cachecontrol_nocache",
            "ns_cachecontrol_nocache_adv",
            "ns_header_pragma",
            "ns_header_pragma_adv",
            "ns_header_cookie",
            "ns_header_cookie_adv",
            "ns_ext_cgi",
            "ns_ext_cgi_adv",
            "ns_ext_asp",
            "ns_ext_asp_adv",
            "ns_ext_exe",
            "ns_ext_exe_adv",
            "ns_ext_cfm",
            "ns_ext_cfm_adv",
            "ns_ext_ex",
            "ns_ext_ex_adv",
            "ns_ext_shtml",
            "ns_ext_shtml_adv",
            "ns_ext_htx",
            "ns_ext_htx_adv",
            "ns_url_path_cgibin",
            "ns_url_path_cgibin_adv",
            "ns_url_path_exec",
            "ns_url_path_exec_adv",
            "ns_url_path_bin",
            "ns_url_path_bin_adv",
            "ns_url_tokens",
            "ns_url_tokens_adv",
            "ns_ext_not_gif",
            "ns_ext_not_gif_adv",
            "ns_ext_not_jpeg",
            "ns_ext_not_jpeg_adv",
            "ns_cmpclient",
            "ns_cmpclient_adv",
            "ns_slowclient",
            "ns_slowclient_adv",
            "ns_farclient",
            "ns_content_type"
            "ns_msword",
            "ns_msexcel",
            "ns_msppt",
            "ns_css",
            "ns_css_adv",
            "ns_xmldata",
            "ns_xmldata_adv",
            "ns_mozilla_47",
            "ns_mozilla_47_adv",
            "ns_msie",
            "ns_msie_adv",
            "ns_audio",
            "ns_video",
            "av_5_Symantec_7_5",
            "av_5_Symantec_6_0",
            "av_5_Symantec_10",
            "av_5_Mcafee",
            "pf_5_sygate_5_6",
            "pf_5_zonealarm_6_5",
            "av_5_sophos_4",
            "av_5_sophos_5",
            "av_5_sophos_6",
            "is_5_norton",
            "av_5_TrendMicro_11_25",
            "av_5_McAfeevirusscan_11",
            "av_5_TrendMicroOfficeScan_7_3",
            "pf_5_TrendMicroOfficeScan_7_3",
            "ns_content_type_advanced",
            "ns_msword_advanced",
            "ns_msexcel_advanced",
            "ns_msppt_advanced",
            "rqd_is_yt_domain",
            "rqd_is_yt_abr",
            "rqd_is_yt_otherpd",
            "rqd_is_yt_pd_1"
            "ns_videoopt_netflix_abr_ssl",
            "ns_videoopt_pd_abr_detection",
    ]

    @staticmethod
    def register_built_in_named_exprs():
        """
        Register built-in classic Named expression names in
        classic_entities_names.
        """
        for classic_exp_name in NamedExpression.built_in_named_expr:
            classic_entities_names.add(classic_exp_name)

    @common.register_for_cmd("add", "policy", "expression")
    def check_policy_expr(self, commandParseTree):
        """
            This checks whether the expression is classic or
            advanced. If it is an advanced expression, then
            it checks whether any removed advanced expression
            is being used or not. And if it classic, then checks
            whether name is correct for the advanced expression,
            and whether classic expression can be converted to
            advanced or not.

            Classic named expression name is not
            valid for advanced expression if:
            1. It the name is same as one of the Policy
               entity (patset/dataset/stringmap/
               variable/hmacKey/EncriptionKey/callout) name.
            2. it doesn't start with ASCII alphabetic character or underscore.
            3. it has characters other than ASCII alphanumerics
               or underscore characters.
            4. it is equal to a advanced policy expression reserved word (prefix identifier or
               enum value)
        """
        reserved_word_list = set(
            [ # Advanced policy expression prefix list
             "subscriber",
             "connection",
             "analytics",
             "diameter",
             "target",
             "server",
             "radius",
             "oracle",
             "extend",
             "client",
             "mysql",
             "mssql",
             "false",
             "true",
             "text",
             "smpp",
             "icap",
             "http",
             "url",
             "sys",
             "sip",
             "ica",
             "dns",
             "aaa",
             "re",
             "xp",
             "ce"
             ])

        expr_name = commandParseTree.positional_value(0).value
        expr_rule = commandParseTree.positional_value(1).value
        lower_expr_name = expr_name.lower()

        # Ignore the saved builtin expressions
        if lower_expr_name in NamedExpression.built_in_named_expr_list:
            return []

        if (lower_expr_name in policy_entities_names):
            logging.error("Name {} is already in use".format(expr_name))

        if (lower_expr_name in reserved_word_list):
            logging.error(("Expression name {} is invalid for advanced "
                           "expression: names must begin with an ASCII "
                           "alphabetic character or underscore and must "
                           "contain only ASCII alphanumerics or underscores"
                           " and shouldn't be name of another policy entity"
                           "; words reserved for policy use may not be used;"
                           " underscores will be substituted for any invalid"
                           " characters in corresponding advanced name")
                          .format(expr_name))

        if commandParseTree.keyword_exists('clientSecurityMessage'):
            NamedExpression.register_classic_entity_name(commandParseTree)

        named_expr[lower_expr_name] = expr_rule

        original_tree = copy.deepcopy(commandParseTree)
        commandParseTree = NamedExpression \
            .check_pos_expr(commandParseTree, 1, False)

        if commandParseTree.invalid:
            """
            Add the commands in the global list which will be used to
            check whether any other expression is using these named
            expressions.
            """
            NamedExpression.register_policy_entity_name(commandParseTree)
            NamedExpression.register_classic_entity_name(original_tree)
        else:
            NamedExpression.register_policy_entity_name(original_tree)
            if is_advanced_removed_expr_present(expr_rule):
                return [commandParseTree]
        return []


@common.register_class_methods
class HTTPProfile(CheckConfig):
    """ Handle HTTP Profile """

    @common.register_for_cmd("add", "ns", "httpProfile")
    @common.register_for_cmd("set", "ns", "httpProfile")
    def check_spdy(self, commandParseTree):
        """
        Check if spdy parameter present in HTTP profile.
        Syntax:
        """
        if commandParseTree.keyword_exists('spdy'):
            commandParseTree.set_invalid()
            return [commandParseTree]
        HTTPProfile.check_adv_expr_list(commandParseTree, ["clientIpHdrExpr"])
        if commandParseTree.invalid:
            return [commandParseTree]
        return []


@common.register_class_methods
class ContentSwitching(CheckConfig):
    """ Check Content Switching feature """

    @common.register_for_cmd("add", "cs", "policy")
    def check_cs_policy(self, commandParseTree):
        if commandParseTree.keyword_exists('action'):
            ContentSwitching.check_adv_expr_list(commandParseTree, ["rule"])
            if commandParseTree.invalid:
                return [commandParseTree]
            return []
        if commandParseTree.keyword_exists('rule'):
            if commandParseTree.keyword_exists('domain'):
                    commandParseTree.set_invalid()
                    return [commandParseTree]
            else:
                commandParseTree = ContentSwitching \
                    .check_keyword_expr(commandParseTree, 'rule')
                if commandParseTree.invalid:
                    return [commandParseTree]
        elif commandParseTree.keyword_exists('url'):
            commandParseTree.set_invalid()
            return [commandParseTree]
        elif commandParseTree.keyword_exists('domain'):
            commandParseTree.set_invalid()
            return [commandParseTree]

        return []


@common.register_class_methods
class CMP(CheckConfig):
    """
    Checks CMP feature commands.
    """

    # Classic built-in policy names.
    built_in_policies = [
        "ns_cmp_content_type",
        "ns_cmp_msapp",
        "ns_cmp_mscss",
        "ns_nocmp_mozilla_47",
        "ns_nocmp_xml_ie"
    ]

    @common.register_for_cmd("set", "cmp", "parameter")
    def set_cmp_parameter(self, cmp_param_tree):
        if cmp_param_tree.keyword_exists("policyType"):
            self._initial_cmp_parameter = \
                cmp_param_tree.keyword_value("policyType")[0].value.lower()
            if self._initial_cmp_parameter == "classic":
                cmp_param_tree.set_invalid()
                return [cmp_param_tree]
        return []

    @common.register_for_cmd("set", "cmp", "policy")
    def set_cmp_policy(self, cmp_policy_tree):
        policy_name = cmp_policy_tree.positional_value(0).value
        if policy_name in self.built_in_policies:
            cmp_policy_tree.set_invalid()
            return [cmp_policy_tree]
        return []

    @common.register_for_cmd("add", "cmp", "policy")
    def check_cmp_policy(self, cmp_policy_tree):
        CheckConfig.check_keyword_expr(cmp_policy_tree, 'rule')
        if cmp_policy_tree.invalid:
            return [cmp_policy_tree]
        return []

    @common.register_for_cmd("bind", "cmp", "global")
    def check_cmp_global_bind(self, bind_cmd_tree):
        """
        Checks CMP policy bindings to cmp global.
        """
        # If state keyword is present then it is a
        # classic binding.
        if bind_cmd_tree.keyword_exists("state"):
            return [bind_cmd_tree]

        policy_name = bind_cmd_tree.positional_value(0).value
        if policy_name in self.built_in_policies:
            bind_cmd_tree.set_invalid()
            return [bind_cmd_tree]
        return []


@common.register_class_methods
class CLITransformFilter(CheckConfig):
    """
    Checks Filter feature
    """

    @common.register_for_cmd("add", "filter", "action")
    def check_filter_action(self, action_parse_tree):
        """
        Check Filter action
        """
        action_parse_tree.set_invalid()
        return [action_parse_tree]

    @common.register_for_cmd("add", "filter", "policy")
    def check_filter_policy(self, policy_parse_tree):
        """
        Check Filter policy
        """
        policy_parse_tree.set_invalid()
        return [policy_parse_tree]

    @common.register_for_cmd("bind", "filter", "global")
    def check_filter_global_bindings(self, bind_parse_tree):
        """
        Check Filter global binding
        """
        bind_parse_tree.set_invalid()
        return [bind_parse_tree]

    @common.register_for_cmd("add", "filter", "htmlinjectionvariable")
    @common.register_for_cmd("set", "filter", "htmlinjectionvariable")
    @common.register_for_cmd("set", "filter", "htmlinjectionparameter")
    @common.register_for_cmd("set", "filter", "prebodyInjection")
    @common.register_for_cmd("set", "filter", "postbodyInjection")
    def check_filter_htmlinjection_command(self, cmd_parse_tree):
        """
        Check Filter HTMLInjection command
        """
        cmd_parse_tree.set_invalid()
        return [cmd_parse_tree]


@common.register_class_methods
class Rewrite(CheckConfig):
    """
    Check rewrite action
    """

    @common.register_for_cmd("add", "rewrite", "action")
    def check_rewrite_action(self, tree):
        if tree.keyword_exists('pattern'):
            tree.set_invalid()
            return [tree]
        if tree.keyword_exists('bypassSafetyCheck'):
            tree.set_invalid()
            return [tree]
        Rewrite.check_adv_expr_list(tree, [2, 3, "refineSearch"])
        if tree.invalid:
            return [tree]
        return []


@common.register_class_methods
class LB(CheckConfig):
    """
    Check LB persistence rule
    """

    @common.register_for_cmd("add", "lb", "vserver")
    def check_lb_rule(self, commandParseTree):
        commandParseTree = LB.check_keyword_expr(commandParseTree, 'rule')
        if commandParseTree.invalid:
            return [commandParseTree]
        LB.check_adv_expr_list(
            commandParseTree, ["Listenpolicy", "resRule", "pushLabel"])
        if commandParseTree.invalid:
            return [commandParseTree]
        return []


@common.register_class_methods
class SureConnect(CheckConfig):
    """
    Check SureConnect commands
    """

    @common.register_for_cmd("add", "sc", "policy")
    @common.register_for_cmd("set", "sc", "parameter")
    def check_sc_policy(self, tree):
        tree.set_invalid()
        return [tree]


@common.register_class_methods
class PriorityQueuing(CheckConfig):
    """
    Check PriorityQueuing commands
    """

    @common.register_for_cmd("add", "pq", "policy")
    def check_sc_policy(self, tree):
        tree.set_invalid()
        return [tree]


@common.register_class_methods
class HDoSP(CheckConfig):
    """
    Check HTTP Denial of Service Protection commands
    """

    @common.register_for_cmd("add", "dos", "policy")
    def check_dos_policy(self, tree):
        tree.set_invalid()
        return [tree]


@common.register_class_methods
class AdvExpression(CheckConfig):
    """
    Handles conversion of Q and S prefixes, HTTP.REQ.BODY and
    SYS.EVAL_CLASSIC_EXPR expression in commands
    which allows only advanced expressions.
    """

    @common.register_for_cmd("add", "rewrite", "policy")
    @common.register_for_cmd("add", "responder", "policy")
    @common.register_for_cmd("add", "cs", "vserver")
    @common.register_for_cmd("add", "videooptimization", "detectionpolicy")
    @common.register_for_cmd("add", "dns", "policy")
    @common.register_for_cmd("add", "cache", "selector")
    @common.register_for_cmd("add", "cs", "action")
    @common.register_for_cmd("add", "vpn", "clientlessAccessPolicy")
    @common.register_for_cmd("add", "authentication", "webAuthAction")
    @common.register_for_cmd("set", "authentication", "webAuthAction")
    @common.register_for_cmd("add", "tm", "trafficPolicy")
    @common.register_for_cmd("add", "authentication", "samlIdPPolicy")
    @common.register_for_cmd("add", "feo", "policy")
    @common.register_for_cmd("add", "cache", "policy")
    @common.register_for_cmd("add", "transform", "policy")
    @common.register_for_cmd("add", "appqoe", "action")
    @common.register_for_cmd("add", "appqoe", "policy")
    @common.register_for_cmd("add", "appflow", "policy")
    @common.register_for_cmd("add", "autoscale", "policy")
    @common.register_for_cmd("add", "authentication", "Policy")
    @common.register_for_cmd("add", "authentication", "loginSchemaPolicy")
    @common.register_for_cmd("add", "authentication", "loginSchema")
    @common.register_for_cmd("add", "gslb", "vserver")
    @common.register_for_cmd("add", "ns", "assignment")
    @common.register_for_cmd("add", "dns", "action64")
    @common.register_for_cmd("add", "dns", "policy64")
    @common.register_for_cmd("add", "authentication", "OAuthIdPPolicy")
    @common.register_for_cmd("add", "authentication", "samlIdPProfile")
    @common.register_for_cmd("add", "contentInspection", "policy")
    @common.register_for_cmd("add", "ica", "policy")
    @common.register_for_cmd("add", "lb", "group")
    @common.register_for_cmd("add", "audit", "messageaction")
    @common.register_for_cmd("add", "spillover", "policy")
    @common.register_for_cmd("add", "stream", "selector")
    @common.register_for_cmd("add","tm", "formSSOAction")
    @common.register_for_cmd("add", "tm", "samlSSOProfile")
    @common.register_for_cmd("add", "vpn", "sessionPolicy")
    @common.register_for_cmd("add", "vpn", "trafficAction")
    @common.register_for_cmd("add", "vpn", "vserver")
    @common.register_for_cmd("set", "uiinternal", "EXPRESSION")
    def check_advanced_expr(self, commandParseTree):
        """
        Commands which allows ONLY advanced expressions should be registered for this method.
        Handles conversion of Q and S prefixes and SYS.EVAL_CLASSIC_EXPR expression.
        Each command that will be registered to this method, should add an entry in
        command_parameters_list.
        """

        # Each command should mention the list of parameters where advanced expression
        # can be used. Only these parameters will be checked for SYS.EVAL_CLASSIC_EXPR
        # expression.
        # If its a keyword parameter, mention the keyword name.
        # If its a positional parameter, mention the position of the parameter.
        command_parameters_list = {
            "add rewrite policy": [1],
            "add responder policy": [1],
            "add cs vserver": ["Listenpolicy", "pushLabel"],
            "add videooptimization detectionpolicy": ["rule"],
            "add videooptimization pacingpolicy": ["rule"],
            "add dns policy": [1],
            "add cache selector": [1, 2, 3, 4, 5, 6, 7, 8],
            "add cs action": ["targetVserverExpr"],
            "add vpn clientlessaccesspolicy": [1],
            "add authentication webauthaction": ["fullReqExpr", "successRule"],
            "set authentication webauthaction": ["fullReqExpr", "successRule"],
            "add tm trafficpolicy": [1],
            "add authentication samlidppolicy": ["rule"],
            "add feo policy": [1],
            "add cache policy": ["rule"],
            "add transform policy": [1],
            "add appqoe action": ["dosTrigExpression"],
            "add appqoe policy": ["rule"],
            "add ssl policy": ["rule"],
            "add appflow policy": [1],
            "add autoscale policy": ["rule"],
            "add authentication policy": ["rule"],
            "add authentication loginschemapolicy": ["rule"],
            "add authentication loginschema": ["userExpression", "passwdExpression"],
            "add gslb vserver": ["rule"],
            "add ns assignment": ["set", "append", "add", "sub"],
            "add dns action64": ["mappedRule", "excludeRule"],
            "add dns policy64": ["rule"],
            "add authentication oauthidppolicy": ["rule"],
            "add authentication samlidpprofile": ["NameIDExpr", "acsUrlRule"],
            "add contentinspection policy": ["rule"],
            "add ica policy": ["rule"],
            "add lb group": ["rule"],
            "add audit messageaction": [2],
            "add spillover policy": ["rule"],
            "add stream selector": [1, 2, 3, 4, 5],
            "add tm formssoaction": ["ssoSuccessRule"],
            "add tm samlssoprofile": ["relaystateRule", "NameIDExpr"],
            "add vpn sessionpolicy": [1],
            "add vpn trafficaction": ["userExpression", "passwdExpression"],
            "add vpn vserver": ["Listenpolicy"],
            "set uiinternal expression": ["rule"],
        }

        command = " ".join(commandParseTree.get_command_type()).lower()
        if command in command_parameters_list:
            AdvExpression.check_adv_expr_list(commandParseTree, command_parameters_list[command])
            if commandParseTree.invalid:
                return [commandParseTree]
        return []



@common.register_class_methods
class Responder(CheckConfig):
    """
    Check responder commands
    """

    @common.register_for_cmd("add", "responder", "action")
    def check_responder_action(self, commandParseTree):
        """
        Check the responder action for the removed
        advanced expressions and NOOP action type.
        """
        Responder.check_adv_expr_list(
            commandParseTree, [2, "reasonPhrase", "headers"])
        if commandParseTree.invalid:
            return [commandParseTree]
        return []


@common.register_class_methods
class NSFeatures(CheckConfig):
    """ Handles enable ns feature command """

    @common.register_for_cmd("enable", "ns", "feature")
    def check_ns_feature(self, commandParseTree):
        """
        Throw error for SC, PQ and HDOSP features
        """
        features_to_check = ["SC", "PQ", "HDOSP", "CF"]
        num_of_enabled_features = commandParseTree.get_number_of_params()
        for inx in range(num_of_enabled_features):
            feature_node = commandParseTree.positional_value(inx)
            feature_name = feature_node.value
            if feature_name in features_to_check:
                return [commandParseTree]
        return []
