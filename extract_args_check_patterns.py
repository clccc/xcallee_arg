# coding:utf-8
# -----------------------------
# code by cl in 2019-01-02
# use Joern to extract raw explict-check and implicit-check of every callee, which is call instance of
# the argument-sensitive function @function_name interested
# -----------------------------

from threading import Thread
from database_provider import DBContentsProvider
from ObjDataAndBinFile import ObjDataAndBinFile


class ExtractArgsCheckPatterns:
    def __init__(self, function_name):
        self.db_provider = DBContentsProvider()
        self.file_io_provider = ObjDataAndBinFile()
        self.function_name = function_name
        self.count_threads = 20

    def set_implicit_check_pattern(self, arg_checked, arg_by):
        # CNT is constant, OutVar is variable from outside of caller
        if arg_by == "CNT":
            return "arg_%s <- %s" % (arg_checked, arg_by)
        if arg_by == "OutVar":
            return "arg_%s <- %s" % (arg_checked, arg_by)
        return "arg_%s <- arg_%s" % (arg_checked, arg_by)

    def set_explicit_check_pattern(self, arg_checked, checkinfo):

        flowlabel_code = checkinfo[0][0]
        operator_code = checkinfo[1]
        related_args = checkinfo[2]
        pattern_str = "%s %s arg_%s VS (" % (arg_checked, flowlabel_code, operator_code)
        for arg_index in related_args:
            pattern_str += " arg_%s " % arg_index
        pattern_str += ")"
        return

    def run_gremlin_query(self, query):
        return self.db_provider.run_gremlin_query(query)

    def save_data_to_file(self, data, file_path):
        # filename = "Data/OutStatsData_%s.data"%time.strftime('%Y%m%d-%H%M%S')
        # print "生成GetOutStatsData的原始数据文件:%s" % file_path
        self.file_io_provider.objdata2file(data, file_path)

    def query_callee_ids(self, function_name):
        query = """
        g.V().has('type','Callee').has('code','%s').id.toList()
        """ % function_name
        callee_ids = self.run_gremlin_query(query)
        return callee_ids

    def query_callsite_id(self, callee_id):
        query = """
        g.v(%s).in.in.id
        """ % callee_id
        callsite_id = self.run_gremlin_query(query)
        return callsite_id[0]

    def query_backward_paths(self, callee_id):
        query = """
        getBackwardPaths(%s)
        """ % callee_id
        all_paths = self.run_gremlin_query(query)
        return all_paths

    # def_chain = src.id <--var_str-- dst.id
    def query_define_chains(self, path):
        def_chain = []
        for node_id in path:
            query = """
            g.v(%s).inE('REACHES').transform{[it.inV.id, it.var, it.outV.id]}
            """ % node_id
            def_chain_tmp = self.run_gremlin_query(query)
            # select the definition of the @path
            for chain in def_chain_tmp:
                if (chain[0][0] in path) and (chain[2][0] in path):
                    # remove the define node which dst == src, it will make some process loop forever
                    if chain[0][0] != chain[2][0]:
                        def_chain.append([chain[0][0], chain[1], chain[2][0]])

        # remove the invalid define chain from @def_chain
        invalid_chains = []
        for i in range(0, len(def_chain)):
            for j in range(0, len(def_chain)):
                if i == j:
                    continue
                # the nearest definition on the same node with the same variable is the valid one
                if def_chain[i][0] == def_chain[j][0] and def_chain[i][1] == def_chain[j][1]:
                    if path.index(def_chain[i][2]) > path.index(def_chain[j][2]):
                        invalid_chains.append(i)
                    else:
                        invalid_chains.append(j)
        invalid_chains = self.unique_list(invalid_chains)
        invalid_chains.sort(reverse=True)
        for i in invalid_chains:
            def_chain.remove(def_chain[i])
        return def_chain

    def query_args(self, callee_id):
        query = """
        getArgs(%s)
        """ % callee_id
        arg_ids = self.run_gremlin_query(query)
        return arg_ids

    def query_symbols_by_ids(self, ids):
        symbols_id = []
        symbols_code = []
        for arg in ids:
            query = """
            _getSymbols(%s)
            """ % arg
            s_ids = self.run_gremlin_query(query)
            symbols_id.append(s_ids)
            s_codes = []
            if s_ids:
                for vid in s_ids:
                    s_codes.append(self.query_code_by_id(vid))
            else:
                s_codes.append(u'')
            symbols_code.append(s_codes)
        return symbols_id, symbols_code

    def query_define_vars_dst_on_symbols(self, src_id, symbols, def_chain):
        define_vars = []
        define_dst_node = []
        callsite = src_id
        for s in symbols:
            var_symbol = self.query_code_by_id(s)
            head_node = self.search_dst_by_var_src(callsite, var_symbol, def_chain)
            if not head_node:
                continue
            define_vars.append(var_symbol)
            define_dst_node.append(head_node)
            src_nodes = [head_node]
            while src_nodes:
                src_new = []
                for src in src_nodes:
                    middle_define_vars, dst_nodes = self.search_vars_dsts_by_src(src, def_chain)
                    if middle_define_vars:
                        for dst in dst_nodes:
                            if dst not in define_dst_node:
                                src_new.extend(dst_nodes)

                            define_vars.extend(middle_define_vars)
                            define_dst_node.extend(dst_nodes)

                src_nodes = src_new
            #define_dst_node = self.unique_list(define_dst_node)
            #define_vars = self.unique_list(define_vars)
        return define_vars, define_dst_node

    def query_code_by_id(self, vid):
        query = """
        _getCodeById(%s)
        """ % vid
        code = self.run_gremlin_query(query)
        return code

    # search dst node from def_chain by var and src node
    def search_dst_by_var_src(self, src, var, def_chain):
        for def_node in def_chain:
            if src == def_node[0] and var == def_node[1]:
                return def_node[2]
        return False

    def search_vars_dsts_by_src(self, src, def_chain):
        define_vars = []
        dst_nodes = []
        for def_node in def_chain:
            if def_node[0] == src:
                define_vars.append(def_node[1])
                dst_nodes.append(def_node[2])
        return define_vars, dst_nodes

    def query_flowlabel_between_nodes(self, out_v, in_v):
        query = """
        _getFlowlabelOfCfgIds(%s, %s)
        """ % (out_v, in_v)
        flowlabel = self.run_gremlin_query(query)
        return flowlabel

    def query_parsed_control(self, control_id, next_node):
        query = """
        parseControl(%s,%s)
        """ % (control_id, next_node)
        control_info = self.run_gremlin_query(query)

        flowlabel_code = control_info[0]
        operate_code = control_info[1]
        children = control_info[2]
        return flowlabel_code, operate_code, children

    # the controls are condition statements control the callsite_id
    def query_controls(self, callsite_id):
        query = """4849840
        getControlsFromCfgId(%s)
        """ % callsite_id
        controls = self.run_gremlin_query(query)
        return controls

    # get controls of the path
    def query_controls_path(self, controls, path):
        controls_path = []
        for c in controls:
            if c in path:
                controls_path.append(c)
        return controls_path

    def query_control_symbols(self, control):
        query = """
        _getSymbols(%s)
        """ % control
        control_symbols = self.run_gremlin_query(query)
        return control_symbols

    @staticmethod
    def unique_list(old_list):
        new_list = []
        for i in old_list:
            if i not in new_list:
                new_list.append(i)
        return new_list

    @staticmethod
    def is_lists_cross(list1, list2):
        for l in list1:
            if l in list2:
                return True
        return False

    @staticmethod
    def get_index_same_items_of_list1(list1, list2):
        indexList = []
        for i in range(0,len(list1)):
            if list1[i] in list2:
                indexList.append(i)
        return indexList

    @staticmethod
    def list1_VSset_list2(list1,list2):
        if set(list1) > set(list2):
            return '>'
        if set(list1) == set(list2):
            return '='
        if set(list1) < set(list2):
            return '<'
        else:
            return 'x'

    def query_check_patterns_path(self, callee_id, callsite_id, path, controls_path):
        arg_ids = self.query_args(callee_id)
        symbols_id_of_args, symbols_code_of_args = self.query_symbols_by_ids(arg_ids)
        def_chain_path = self.query_define_chains(path)
        define_vars_of_args = []
        define_dst_of_args = []
        for symbols_arg in symbols_id_of_args:
            defvars_of_arg, define_dst_of_arg = \
                self.query_define_vars_dst_on_symbols(callsite_id, symbols_arg, def_chain_path)
            define_vars_of_args.append(defvars_of_arg)
            define_dst_of_args.append(define_dst_of_arg)

        arg_num = len(arg_ids)

        # I. 隐式约束 query_implicit_check_patterns_path
        implicit_check_patterns = [[] for i in range(arg_num)]
        '''
        for i in range(0, arg_num):
            # 1. 判断该参数是否为常量
            #   1.1 没有用到符号
            if not symbols_id_of_args[i]:
                implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, "CNT"))
                continue

            # Because Joern can not identify the Global variable/const,
            # the arg may have symbol but its define_vars_of_args is NULL.
            # Because the global variable is not recommend, used rarely,
            # so we set its check pattern as defined by const  "CNT"
            # const: type 'PrimaryExpression'
            #   1.2 有符号没却没有用于定义的变量，见全局变量，Joern不精准的原因
            if symbols_id_of_args[i] and (not define_vars_of_args[i]):
                implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, "CNT"))
                continue

            # If the right values of all the define nodes of the define chains' tails (define_dst_of_args[i]) are constants,
            # the arg is defined by constant
            #   1.3. 所有的定义语句都是常量赋值，那么最终的实参也是常量
            flag_value = True
            if define_dst_of_args[i]:
                for nodeid in define_dst_of_args[i]:
                    nodecode = self.run_gremlin_query("g.v(%s).code" % nodeid)
                    value = nodecode.split("=", 1)
                    if len(value) != 2:
                        flag_value = False
                        break
                    rightvalue = value[1]
                    # 此处有错误，如果是字符串常量呢？
                    if rightvalue.isdigit() != True:
                        flag_value = False
                        break
                if flag_value:
                    implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, "CNT"))
                    continue
            for j in range(i + 1, arg_num):
                # 2. 判断与其它参数的关系
                #   2.1. symbols属于包含关系
                if self.list1_VSset_list2(symbols_id_of_args[i], symbols_id_of_args[j]) == '>':
                    implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, j))
                    continue
                #if self.is_lists_cross(symbols_id_of_args[i], symbols_id_of_args[j]):
                #    implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, j))
                if self.list1_VSset_list2(symbols_id_of_args[i], symbols_id_of_args[j]) == '<':
                    implicit_check_patterns[j].append(self.set_implicit_check_pattern(j, i))
                    continue
                if self.list1_VSset_list2(symbols_id_of_args[i], symbols_id_of_args[j]) == '=':
                    implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, j))
                    implicit_check_patterns[j].append(self.set_implicit_check_pattern(j, i))
                    continue

                #   2.2. var包含关系
                if self.list1_VSset_list2(define_vars_of_args[i], symbols_code_of_args[j]) == '>':
                    implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, j))
                    continue
                if self.list1_VSset_list2(define_vars_of_args[j], symbols_code_of_args[i]) == '>':
                    implicit_check_patterns[i].append(self.set_implicit_check_pattern(j, i))
                    continue

                tmp_defvar_i = define_vars_of_args[i][1:len(define_vars_of_args[i])]
                tmp_defvar_j = define_vars_of_args[j][1:len(define_vars_of_args[j])]
                if tmp_defvar_j:
                    if self.list1_VSset_list2(define_vars_of_args[i], tmp_defvar_j) == '>':
                        implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, j))
                        continue
                if tmp_defvar_i:
                    if self.list1_VSset_list2(define_vars_of_args[j], tmp_defvar_i) == '>':
                        implicit_check_patterns[i].append(self.set_implicit_check_pattern(j, i))
                        continue
                if tmp_defvar_i and tmp_defvar_j:
                    if self.list1_VSset_list2(tmp_defvar_j, tmp_defvar_i) == '=':
                        implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, j))
                        implicit_check_patterns[i].append(self.set_implicit_check_pattern(j, i))
                        continue

                #   2.3. 混合定义的情况
                if self.is_lists_cross(define_vars_of_args[i], define_vars_of_args[j]):
                    implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, j))
                    implicit_check_patterns[i].append(self.set_implicit_check_pattern(j, i))
                    # implicit_check_patterns[j].append(self.set_implicit_check_pattern(j, i))
                    continue

                # 3. 其它归为未知变量：后续过程间分析时需要区分是否依赖于调用者的入参
                # the default define patten is defined by "OutVar"

                # implicit_check_patterns[i].append(self.set_implicit_check_pattern(i, "OutVar"))
        '''

        # II. 显式约束 query_explicit_check_patterns_path:
        # If there is a define node on one symbol of the @arg, whose location is between the control node @control
        # and the callsite, then the @control is not take an explicit check on the @arg.
        # Else if the defvar(@control) ^ defvar(@arg) != [], then @control is take an explicit check on the @arg.
        explicit_check_patterns = [[] for i in range(arg_num)]
        explicit_checkinfo_args = [[] for i in range(arg_num)]
        checked_arg_control = []
        symbols_id_of_controls, symbols_code_of_controls = self.query_symbols_by_ids(controls_path)
        define_vars_of_controls = []
        define_dst_of_controls = []
        for symbols_control in symbols_id_of_controls:
            defvars_of_control, define_dst_of_control = \
                self.query_define_vars_dst_on_symbols(callsite_id, symbols_control, def_chain_path)
            define_vars_of_controls.append(defvars_of_control)
            define_dst_of_controls.append(define_dst_of_control)

        # 1. 筛选有效的条件检查，并与对应的参数关联
        for index_arg in range(0, arg_num):
            for index_control in range(0, len(controls_path)):
                checked_var_of_args = self.get_index_same_items_of_list1(define_vars_of_args[index_arg],
                                                   define_vars_of_controls[index_control])
                location_control = path.index(controls_path[index_control])
                if checked_var_of_args:
                    flag_valid_control = True
                    for index_checked_var_of_args in checked_var_of_args:
                        location_checked_dst_node = path.index(define_dst_of_args[index_checked_var_of_args])
                        # if one control check on var, but the var was defined again after the control,
                        # then the control is not consided as a valid check on var
                        if location_control > location_checked_dst_node:
                            flag_valid_control = False
                            break
                    if flag_valid_control:
                        # log the relation between arg and valid controls
                        checked_arg_control.append([index_arg, index_control])

        # 2.解析有效的条件检查；收集条件检查的 逻辑运算符号，结果满足条件（True，False），相关参数
        # collect check info from @checked_arg_control into each arg
        for c_arg_control in checked_arg_control:
            index_arg = c_arg_control[0]
            index_control = c_arg_control[1]

            # get some useful control information
            # self.query_parsed_control(controls_path[index_control],
            #                           controls_path[index_control - 1])  is wrong
            index_next_node = path.index(controls_path[index_control]) - 1
            flowlabel_code, operate_code, children = \
                self.query_parsed_control(controls_path[index_control], path[index_next_node])

            args_by_control = []
            for log_check_2 in checked_arg_control:
                if log_check_2[1] == index_control:
                    if log_check_2[0] != index_arg:
                        args_by_control.append(log_check_2[0])
            args_by_control = self.unique_list(args_by_control)
            args_by_control.sort()
            explicit_checkinfo_args[index_arg].append([flowlabel_code, operate_code, args_by_control])

        for index_arg in range(0, arg_num):
            for checkinfo in explicit_checkinfo_args[index_arg]:
                explicit_check_patterns[index_arg].append(
                    self.set_explicit_check_pattern(arg_checked=index_arg, checkinfo=checkinfo))

        # 去重
        for i in range(0, len(implicit_check_patterns)):
            implicit_check_patterns[i] = self.unique_list(implicit_check_patterns[i])
        for i in range(0, len(explicit_check_patterns)):
            explicit_check_patterns[i] = self.unique_list(explicit_check_patterns[i])

        return implicit_check_patterns, explicit_check_patterns

    def query_check_patterns_path_thread(self, callee_id, callsite_id, path, controls_path, result, index):
        implicit_check_patterns, explicit_check_patterns = \
            self.query_check_patterns_path(callee_id, callsite_id, path, controls_path)

        result[index] = [implicit_check_patterns, explicit_check_patterns]
        return result

    def run_no_thread(self, callee_ids):
        check_patterns = []
        check_patterns_callee = []
        i = 0
        # -test
        print "len(callee_ids) = %d " % (len(callee_ids))
        # -test
        for callee_id in callee_ids:
            i = i+1
            # get callsite_id = cfgnodid of callee_id
            callsite_id = self.query_callsite_id(callee_id)
            # -test
            print "%3d.%10d "%(i, callsite_id)
            # -test

            # get controls control the callsite_id
            all_controls = self.query_controls(callsite_id)
            all_paths = self.query_backward_paths(callee_id)

            # -test
            print all_paths
            print "\n"
            # test-


            paths_count = len(all_paths)
            # print "len(all_paths) = %d" % len(all_paths)
            if paths_count == 0:
                check_patterns_callee.append([[], []])
                check_patterns.append([callee_id, check_patterns_callee])
                continue
            else:
                for i in range(0, len(all_paths)):
                    # select control_ids in the path
                    controls_path = self.query_controls_path(all_controls, all_paths[i])
                    implicit_check_patterns, explicit_check_patterns = \
                        self.query_check_patterns_path(callee_id, callsite_id, all_paths[i], controls_path)
                    check_patterns_callee.append([implicit_check_patterns, explicit_check_patterns])

                # #Thinking# if some paths of the same @callee have the same check_patterns,
                # consider some caller has too much paths, that will make bad effect on the measurement of differenct,
                # so we union the same check_patterns
                # 路径约束聚合
                check_patterns_callee = self.unique_list(check_patterns_callee)
                check_patterns.append([callee_id, check_patterns_callee])

        return check_patterns

    # Todo
    def run_thread(self, callee_ids):
        check_patterns = []
        for callee_id in callee_ids:
            check_patterns_callee = []
            callsite_id = self.query_callsite_id(callee_id)
            all_controls = self.query_controls(callsite_id)
            all_paths = self.query_backward_paths(callee_id)
            paths_count = len(all_paths)
            # print "len(all_paths) = %d" % len(all_paths)
            if paths_count == 0:
                check_patterns_callee.append([[], []])
                check_patterns.append([callee_id, check_patterns_callee])
                continue
            else:
                index_path = 0
                while index_path < paths_count:
                    threads = [[] for i in range(self.count_threads)]
                    results_thread = [[] for i in range(self.count_threads)]
                    threads_count = 0
                    for j in range(self.count_threads):
                        if index_path < paths_count:
                            controls_path = self.query_controls_path(all_controls, all_paths[index_path])
                            threads[j] = Thread(target=self.query_check_patterns_path_thread,
                                                args=(callee_id, callsite_id, all_paths[index_path],
                                                      controls_path, results_thread, j))
                            threads_count = threads_count + 1
                            threads[j].start()
                            index_path = index_path + 1
                    for t in range(threads_count):
                        threads[t].join()
                    for t in range(threads_count):
                        check_patterns_callee.append(results_thread[t])
                    # print "\t index_path = %d" % index_path

                # #Thinking# if some paths of the same @callee have the same check_patterns,
                # consider some caller has too much paths, that will make bad effect on the measurement of differenct,
                # so we union the same check_patterns
                check_patterns_callee = self.unique_list(check_patterns_callee)
                check_patterns.append([callee_id, check_patterns_callee])
        return check_patterns

    def run(self, flag_thread=True, *callee_from):
        if len(callee_from):
            if isinstance(callee_from[0], list):
                callee_ids = callee_from[0]
                filepath = "Data/%s.data" % callee_ids[0]
        else:
            callee_ids = self.query_callee_ids(self.function_name)
            filepath = "Data/%s.data" % self.function_name

        if flag_thread:
            check_patterns = self.run_thread(callee_ids)
        else:
            check_patterns = self.run_no_thread(callee_ids)
        print "check_patterns =： "
        print check_patterns
        ObjDataAndBinFile.objdata2file(check_patterns, filepath)
        return check_patterns


if __name__ == '__main__':
    import datetime

    start_time = datetime.datetime.now()
    print "\nBegin time: %s \n" % start_time
    # callee_ids = [6193056]
    # callee_ids = [4994242]
    callee_ids = [42153]
    function_name = "BUF_strlcat"

    extract_check_patterns = ExtractArgsCheckPatterns(function_name)
    patterns = extract_check_patterns.run(False, callee_ids)
    #patterns = extract_check_patterns.run(flag_thread=False)

    """
    flowlabel_code, operate_code, children = \
        extract_check_patterns.query_parsed_control(6638, 6651)
    """

    end_time = datetime.datetime.now()
    print "\nTime Used: %s (%s ~ %s)" % ((end_time - start_time), start_time, end_time)