#!/usr/bin/env python

# Copyright 2021-2023 Citrix Systems, Inc.  All rights reserved.
# Use of this software is governed by the license terms, if any,
# which accompany or are included with this software.

from nspepi_parse_tree import *
import convert_cli_commands as cli_cmds
from cli_lex import *

@common.register_class_methods
class Rewrite(cli_cmds.ConvertConfig):
    """
    Handles Rewrite feature to store few information for
        filter bind conversion
    rw_req_global_goto_exists - Set this true if existing rewrite policy is
               globally bound at the request side with GOTO END/USE_INVOCATION_RESULT
    rw_res_global_goto_exists - Set this true if existing rewrite policy is
               globally bound at the response side with GOTO END/USE_INVOCATION_RESULT
    rw_req_vserver_goto_exists - Set this true if existing rewrite policy is bound
               to vserver at the request side with GOTO END/USE_INVOCATION_RESULT
    rw_res_vserver_goto_exists - Set this true if existing rewrite policy is bound
               to vserver at the response side with GOTO END/USE_INVOCATION_RESULT
    """
    rw_req_global_goto_exists = False
    rw_res_global_goto_exists = False
    rw_req_vserver_goto_exists = False
    rw_res_vserver_goto_exists = False

    @staticmethod
    def is_pattern_regex(pattern):
        """
            Helper function to check whether the
            given pattern is a regex pattern or
            a text string.
        """
        pat_len = len(pattern)
        if (pat_len < 5):
            return (False)
        delimiter = pattern[2]
        r_pat = pattern[0].lower()
        e_pat = pattern[1].lower()
        if ((r_pat != 'r') or (e_pat != 'e') or
            (pattern[pat_len - 1] != delimiter) or
            Lexer.adv_ident_char(delimiter)):
            return (False)
        return (True)

    @common.register_for_cmd("add", "rewrite", "action")
    def convert_rewrite_action(self, tree):
        if cli_cmds.no_conversion_collect_data:
            tree = Rewrite.convert_adv_expr_list(tree, [2, 3, "refineSearch"])
            return []
        if tree.keyword_exists('pattern'):
            pattern_value = tree.keyword_value('pattern')[0].value
            tree.remove_keyword('pattern')
            search_key = CLIKeywordName('search')
            if Rewrite.is_pattern_regex(pattern_value):
                search_val = "regex(" + pattern_value +  ")"
            else:
                tree_obj = CLIParseTreeNode()
                pattern_value = tree_obj.normalize(pattern_value, True)
                search_val = "text(" + pattern_value +  ")"
            search_val_param = CLIKeywordParameter(search_key)
            search_val_param.add_value(search_val)
            tree.add_keyword(search_val_param)
        if tree.keyword_exists('bypassSafetyCheck'):
            tree.remove_keyword('bypassSafetyCheck')
        tree = Rewrite.convert_adv_expr_list(tree, [2, 3, "refineSearch"])
        return [tree]

    @common.register_for_cmd("add", "rewrite", "policy")
    def convert_rewrite_policy(self, tree):
        """
        Saved policy name in policy_list.
        add rewrite policy <name> <rule> <action>
        """
        if cli_cmds.no_conversion_collect_data:
            tree = Rewrite.convert_adv_expr_list(tree, [1])
            return []
        policy_name = tree.positional_value(0).value
        pol_obj = common.Policy(policy_name, self.__class__.__name__,
                                "advanced")
        common.pols_binds.store_policy(pol_obj)
        tree = Rewrite.convert_adv_expr_list(tree, [1])
        return [tree]

    @common.register_for_cmd("bind", "rewrite", "global")
    def convert_rewrite_global(self, tree):
        """
        Handles rewrite global bind command.
        bind rewrite global <policyName> <priority>
            [<gotoPriorityExpression>] [-type <type>]
        Store GOTO info if GOTO is END/USE_INVOCATION_RESULT for
            HTTP/SSL vservers
        tree - bind command parse tree
        """
        if cli_cmds.no_conversion_collect_data:
            return []
        # If no filter policy is configured, then no need to process
        # rewrite bindings
        if not cli_cmds.filter_policy_exists:
            return [tree]

        get_goto_arg = tree.positional_value(2).value
        policy_name = tree.positional_value(0).value
        get_bind_type = tree.keyword_value("type")[0].value
        module = self.__class__.__name__
        priority_arg = 1
        goto_arg = 2
        bind_type_to_check = ["REQ_OVERRIDE", "REQ_DEFAULT",
            "RES_OVERRIDE", "RES_DEFAULT"]
        if get_bind_type in bind_type_to_check:
            if get_goto_arg.upper() in ("END", "USE_INVOCATION_RESULT"):
                # Set below flags only if added vserver is of HTTP/SSL protocol
                if get_bind_type in ("REQ_OVERRIDE", "REQ_DEFAULT"):
                    Rewrite.rw_req_global_goto_exists = True
                else:
                    Rewrite.rw_req_global_goto_exists = True
            self.convert_global_bind(
                tree, tree, policy_name, module, priority_arg, goto_arg)
            return []
        return [tree]

    @common.register_for_bind(["LB", "ContentSwitching", "CacheRedirection"])
    def convert_rewrite_vserver_bindings(
            self, bind_parse_tree, policy_name, priority_arg, goto_arg):
        """
        Handles rewrite policy bindings to vservers - LB, CS, CR
        Syntax for rewrite policy binding:
        bind lb/cr/cs vserver <name> -policyName <string>
            -priority <int> -gotoPriorityExpression <string>
            -type [REQUEST | RESPONSE]
        When rewrite policy is bound:
        1. Store GOTO info if GOTO is END/USE_INVOCATION_RESULT for
             HTTP/SSL vservers
        2. vserver_protocol_dict - dict from cli_cmds and convert_lb_cmd
              packages which carries protocol as value to the key - vserver name
        """
        if cli_cmds.no_conversion_collect_data:
            return []
        # If no filter policy is configured, then no need to process
        # rewrite bindings
        if not cli_cmds.filter_policy_exists:
            return [bind_parse_tree]

        get_goto_arg = bind_parse_tree.keyword_value(
            "gotoPriorityExpression")[0].value
        vs_name = bind_parse_tree.positional_value(0).value.lower()
        policy_name = bind_parse_tree.keyword_value("policyName")[0].value
        flow_type = bind_parse_tree.keyword_value("type")[0].value
        module = self.__class__.__name__
        priority_arg = "priority"
        goto_arg = "gotoPriorityExpression"
        if cli_cmds.vserver_protocol_dict[vs_name] in ("HTTP", "SSL"):
            # Set below flags only if vserver binding policies is of
            # HTTP/SSL protocol
            if get_goto_arg.upper() in ("END", "USE_INVOCATION_RESULT"):
                upper_flow_type = flow_type.upper()
                if upper_flow_type == "REQUEST":
                    Rewrite.rw_req_vserver_goto_exists = True
                elif upper_flow_type == "RESPONSE":
                    Rewrite.rw_res_vserver_goto_exists = True
            self.convert_entity_policy_bind(
                bind_parse_tree, bind_parse_tree, policy_name,
                module, priority_arg, goto_arg)
            return []
        return [bind_parse_tree]
