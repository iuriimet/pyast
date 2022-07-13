#!/usr/bin/env python


import os
import re
import json
import copy


class ASTException(Exception):
    pass


class ASTNode:

    # nodes to be skipped
    # 1. comments nodes
    # Kind of comments:
    #     FullComment, ParagraphComment, TextComment,
    #     InlineCommandComment, HTMLStartTagComment, HTMLEndTagComment,
    #     BlockCommandComment, ParamCommandComment,
    #     TParamCommandComment, VerbatimBlockComment,
    #     VerbatimBlockLineComment, VerbatimLineComment
    skipped_nodes = ['FullComment', 'ParagraphComment', 'TextComment', 'InlineCommandComment', 'HTMLStartTagComment',
                     'HTMLEndTagComment', 'BlockCommandComment', 'ParamCommandComment', 'TParamCommandComment',
                     'VerbatimBlockComment', 'VerbatimBlockLineComment', 'VerbatimLineComment']

    # method nodes
    # CXXConstructorDecl, CXXDestructorDecl
    method_nodes = ['FunctionDecl', 'CXXConstructorDecl', 'CXXDestructorDecl', 'CXXMethodDecl', 'FunctionTemplateDecl']

    # keys that are needed to compare nodes
    used_node_keys = ['id', 'kind', 'name', 'mangledName', 'isUsed', 'type', 'valueCategory', 'value', 'opcode',
                      'castKind', 'isReferenced', 'referencedDecl', 'referencedMemberDecl', 'inner']

    # these keys do not make sense to compare
    forbidden_node_keys = ['loc', 'range']

    def __init__(self, file_pathname: str, node: dict):
        self.file_pathname = file_pathname
        self._id = ''
        self._params = {}
        # parameters that cannot be compared
        self._params_ex = {}
        self._leaves = []

        for k, v in node.items():
            if k in ASTNode.used_node_keys:
                if k == 'id':
                    self._id = v
                elif k == 'type':
                    self._params[k] = v.get('qualType', '')
                elif k == 'referencedDecl':
                    self._params[k] = ASTNode(file_pathname, v)
                elif k == 'referencedMemberDecl':
                    self._params_ex[k] = v
                elif k == 'inner':
                    self._leaves = ASTNode.__parse(file_pathname, v)
                else:
                    self._params[k] = v
            # elif k not in ASTNode.forbidden_node_keys:
            #     print(f'ZZZ ========================= {k} : {v}')

        # some tuning
        # 1. in some cases self.params['type'] may be a string containing the path with line/col numbers, for ex:
        # '(lambda at /home/abuild/rpmbuild/BUILD/capi-context-1.0.6/src/trigger/CustomTemplate.cpp:295:3)'
        t = self._params.get('type', None)
        # todo:
        # just remove the line/col numbers
        # if t:
        #     self.params['type'] = re.sub(r':[0-9]+:[0-9]+', '', t)
        # just remove the whole string
        if t and '/home/abuild/rpmbuild' in t:
            self._params['type'] = ''
        # 2. can't explain
        v = self._params.get('value', None)
        if v:
            k = self._params.get('kind', '')
            vc = self._params.get('valueCategory', '')
            if k == 'IntegerLiteral':
                if vc == 'rvalue':
                    self._params['value'] = ''
            elif k == 'StringLiteral':
                if vc == 'rvalue':
                    self._params['value'] = ''
                elif vc == 'lvalue' and '/home/abuild/rpmbuild' in v:
                    self._params['value'] = ''

    @property
    def uid(self):
        return self._id

    @property
    def kind(self):
        return self._params.get('kind', '')

    @property
    def display_name(self):
        return self._params.get('name', '')

    @property
    def mangled_name(self):
        return self._params.get('mangledName', '')

    def __str__(self):
        return self.__print()

    def __eq__(self, other):
        if not isinstance(other, ASTNode):
            return False

        # check common fields
        if self._params != other._params:
            return False

        # checks for child items
        if len(self._leaves) != len(other._leaves):
            return False
        for node in self._leaves:
            if node not in other._leaves:
                return False

        return True

    def find_methods(self, display_name: str = None, mangled_name: str = None) -> list:
        res = []

        kind = self.kind
        if kind in ASTNode.method_nodes:
            match = True
            if display_name and display_name != self.display_name:
                match = False
            if match and mangled_name and mangled_name != self.mangled_name:
                match = False
            if match:
                res.append(self)
        # elif kind in ['TranslationUnitDecl', 'NamespaceDecl', 'CXXRecordDecl']:
        #     # CXCursor_TranslationUnit -> TranslationUnitDecl
        #     # CXCursor_Namespace -> NamespaceDecl
        #     # CXCursor_ClassDecl
        #     # CXCursor_StmtExpr -> StmtExpr
        #     for leaf in self._leaves:
        #         res.extend(leaf.find_methods(display_name, mangled_name))
        else:
            for leaf in self._leaves:
                res.extend(leaf.find_methods(display_name, mangled_name))

        return res

    def find_referenced_methods(self) -> set:
        res = set()

        ref_node = self._params.get('referencedDecl', None)
        if ref_node and ref_node.kind in ASTNode.method_nodes:
            res.add(ref_node.uid)

        ref_member_node = self._params_ex.get('referencedMemberDecl', None)
        if ref_member_node:
            res.add(ref_member_node)

        for leaf in self._leaves:
            res.update(leaf.find_referenced_methods())

        return res

    @staticmethod
    def __parse(file_pathname: str, nodes: list):
        res = []
        for node in nodes:
            if node.get('kind', '') not in ASTNode.skipped_nodes:
                res.append(ASTNode(file_pathname, node))
        return res

    def __print(self, prefix='|'):
        res = f'{prefix} ASTNode(id: {self._id}, '
        for k, v in self._params.items():
            res += f'{k} : {v}, '
        for k, v in self._params_ex.items():
            res += f'{k} : {v}, '
        res += ')\n'
        for leaf in self._leaves:
            res += leaf.__print(f'{prefix}--')
        return res


class ASTTu:
    def __init__(self, file_pathname: str, node: dict):
        self.file_pathname = file_pathname
        if node.get('kind', '') != 'TranslationUnitDecl':
            raise ASTException(f"TRANSLATION_UNIT not found for {file_pathname}")
        self.root = ASTNode(file_pathname, node)

    def __str__(self):
        return f'{self.file_pathname}:\n{self.root}'

    def find_methods(self, display_name: str = None, mangled_name: str = None) -> list:
        return self.root.find_methods(display_name, mangled_name)


class AST:
    def __init__(self, project_pathname: str):
        self.project_pathname = project_pathname
        self.tu = []
        for ast in AST.__ast_files(project_pathname):
            try:
                with open(ast, encoding="UTF-8") as f:
                    self.tu.append(ASTTu(ast, json.load(f)))
            except ASTException as e:
                print(f"Can't parse ast {ast} : {e}")
            except Exception as e:
                print(f"Can't parse ast {ast} : {e}")
                raise

    def __str__(self):
        res = f'{self.project_pathname}:\n'
        for tu in self.tu:
            res += f'{tu}\n\n'
        return res

    def find_methods(self, display_name: str = None, mangled_name: str = None) -> list:
        res = []
        for tu in self.tu:
            res.extend(tu.find_methods(display_name, mangled_name))
        return res

    @staticmethod
    def __ast_files(project_pathname: str) -> list:
        res = []
        for root, dirs, files in os.walk(project_pathname):
            res.extend([os.path.join(root, f) for f in files if re.search(r'.*\.ast.json$', f)])
        return res


class AffectedFuzzersFinder:

    STATUS_AFFECTED = 'AFFECTED'
    STATUS_NOT_AFFECTED = 'NOT AFFECTED'
    STATUS_IN_PROGRESS = 'IN PROGRESS'

    def __init__(self, report_file_pathname: str, path_to_ast_files1: str, path_to_ast_files2: str):
        # find public APIs (linked to fuzzers)
        self._public_api = AffectedFuzzersFinder.__public_api(report_file_pathname)
        for k, v in self._public_api.items():
            print(f'ZZZ === API: {k} : {v}\n')



        # ast = AST(path_to_ast_files1)
        # print(f'ZZZ === AST: {ast}\n\n\n')


        # build ASTs and find existing methods
        self._existing_methods1 = AST(path_to_ast_files1).find_methods()
        print(f'ZZZ === _existing_methods1 : {len(self._existing_methods1)}\n')
        self._existing_methods2 = AST(path_to_ast_files2).find_methods()
        print(f'ZZZ === _existing_methods2 : {len(self._existing_methods2)}\n')


        # # ZZZ
        # zzz = [z for z in self._existing_methods1 if z.display_name == 'hookRel']
        # for z in zzz:
        #     print(f'ZZZ ================================= HOOK_REL: {z}\n')


        # find modified methods
        self._modified_methods_ids = AffectedFuzzersFinder.__find_modified_methods_ids(self._existing_methods1, self._existing_methods2)
        print(f'ZZZ === modified_methods_ids : {self._modified_methods_ids}\n')

        self._checked_methods = dict()
        self._checked_nodes = dict()

    def __call__(self) -> set:
        res = set()
        # checks is public API affected and get linked fuzzers
        for api, fuzzers in self._public_api.items():
            print(f'ZZZ === CHECK METHOD: {api}')
            if self._checked_methods.get(api, None) is None:
                self._checked_methods[api] = self.__is_method_affected(api)
            if self._checked_methods.get(api, False):
                print(f'ZZZ === METHOD AFFECTED: {api}')
                res.update(fuzzers)
        return res

    def __is_method_affected(self, method_name: str) -> bool:
        # nodes_ids = {n.uid for n in self._existing_methods1
        #              if n.display_name == method_name and n.mangled_name == method_name}
        # for nid in nodes_ids:
        #     if self.__is_node_affected(nid):
        #         return True
        # return False
        return self.__is_nodes_affected({n.uid for n in self._existing_methods1
                                         if n.display_name == method_name and n.mangled_name == method_name})

    def __is_nodes_affected(self, nodes_ids: set) -> bool:
        for nid in nodes_ids:
            # print(f'ZZZ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1 __is_nodes_affected 1: {nid}')
            if self._checked_nodes.get(nid, None) is None:
                # print(f'ZZZ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1 __is_nodes_affected 2: {nid}')
                self._checked_nodes[nid] = AffectedFuzzersFinder.STATUS_IN_PROGRESS
                self._checked_nodes[nid] = AffectedFuzzersFinder.STATUS_AFFECTED \
                    if self.__is_node_affected(nid) else AffectedFuzzersFinder.STATUS_NOT_AFFECTED
                # print(f'ZZZ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1 __is_nodes_affected 3: {nid}: {self._checked_nodes[nid]}')
            if self._checked_nodes.get(nid) == AffectedFuzzersFinder.STATUS_AFFECTED:
                # print(f'ZZZ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! __is_nodes_affected OKK: {nid}')
                return True
        # print(f'ZZZ !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! __is_nodes_affected ERR')
        return False

    def __is_node_affected(self, node_id: str) -> bool:
        # print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 1: {node_id}')
        methods = [m for m in self._existing_methods1 if m.uid == node_id]
        # print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 2: {len(methods)}')
        for method in methods:
            # print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 3: {method.uid}, {method.display_name}, {method.mangled_name}')
            if method.display_name == '' or method.mangled_name == '':
                continue

            nodes = [n for n in self._existing_methods1 if
                     n.display_name == method.display_name and n.mangled_name == method.mangled_name]
            # print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 4: {len(nodes)}')

            for nd in nodes:
                # print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 5: {nd.uid}, {nd.display_name}, {nd.mangled_name}')
                if nd.uid in self._modified_methods_ids:
                    # print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected OK 1: {nd.uid}, {nd.display_name}, {nd.mangled_name}')
                    return True

                # referenced_nodes_ids = nd.find_referenced_methods()
                # for nid in referenced_nodes_ids:
                #
                #     status = self._checked_nodes.get(nid, None)
                #     if status:
                #         if status == AffectedFuzzersFinder.STATUS_AFFECTED:
                #             print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected OK 2: {nid}')
                #             return True
                #     else:
                #         self._checked_nodes[nid] = AffectedFuzzersFinder.STATUS_IN_PROGRESS
                #         if self.__is_node_affected(nid):
                #             print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected OK 3: {nid}')
                #             self._checked_nodes[nid] = AffectedFuzzersFinder.STATUS_AFFECTED
                #             return True
                #         else:
                #             self._checked_nodes[nid] = AffectedFuzzersFinder.STATUS_NOT_AFFECTED
                if self.__is_nodes_affected(nd.find_referenced_methods()):
                    return True

        return False

    @staticmethod
    def __public_api(report_file_pathname: str) -> dict:
        res = dict()
        with open(report_file_pathname) as f:
            report = json.load(f)
            for api in report.get('API', []):
                if api.get('Status', '') != 'GENERATED' or api.get('FuzzerBuildStatus', '') != 'SUCCESS':
                    continue
                name = api.get('Name', None)
                if not name:
                    continue
                fuzzers = []
                for it in api.get('StatusList', []):
                    if it.get('Status', '') != 'GENERATED':
                        continue
                    fuzzer = it.get('StatusFromUT', None)
                    if fuzzer:
                        fuzzers.append(f'{fuzzer}_ftgfuzz')
                res.setdefault(name, set()).update(fuzzers)
        return res

    @staticmethod
    def __find_modified_methods_ids(methods1: list, methods2: list) -> set:
        res = set()
        for m in methods1:
            if m not in methods2:
                print(f'ZZZ === method MODIFIED : {m}\n')
                res.add(m.uid)
        return res


def main():
    fuzzers = AffectedFuzzersFinder('/home/iuriim/tmp/qwe/fuzzGen_Report.json', '/home/iuriim/tmp/qwe/1', '/home/iuriim/tmp/qwe/2')()
    print(f'ZZZ === AFFECTED FUZZERS: {fuzzers}')


if __name__ == '__main__':
    main()



# def is_node_affected(node_id: str, existing_methods: list, modified_methods_ids: set) -> bool:
#     print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 1: {node_id}')
#     methods = [m for m in existing_methods if m.uid == node_id]
#     print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 2: {len(methods)}')
#     for method in methods:
#         print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 3: {method.uid}, {method.display_name}, {method.mangled_name}')
#         if method.display_name == '' or method.mangled_name == '':
#             continue
#         nodes = [n for n in existing_methods if n.display_name == method.display_name and n.mangled_name == method.mangled_name]
#         print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 4: {len(nodes)}')
#         for nd in nodes:
#             print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected 5: {nd.uid}, {nd.display_name}, {nd.mangled_name}')
#             if nd.uid in modified_methods_ids:
#                 print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected OK 1: {nd.uid}, {nd.display_name}, {nd.mangled_name}')
#                 return True
#
#             referenced_nodes_ids = nd.find_referenced_methods()
#             for uid in referenced_nodes_ids:
#                 if is_node_affected(uid, existing_methods, modified_methods_ids):
#                     print(f'ZZZ !!!!!!!!!!!!!!!!!!! is_node_affected OK 2: {uid}')
#                     return True
#
#     return False


# def is_method_affected(method_name: str, existing_methods: list, modified_methods_ids: set) -> bool:
#     method_nodes_ids = {n.uid for n in existing_methods if n.display_name == method_name and n.mangled_name == method_name}
#     for uid in method_nodes_ids:
#         if is_node_affected(uid, existing_methods, modified_methods_ids):
#             return True
#     return False


# def affected_fuzzers(report_file_pathname: str, path_to_ast_files1: str, path_to_ast_files2: str) -> set:
#     res = set()

    # # find public APIs (linked to fuzzers)
    # pub_api = public_api(report_file_pathname)
    # for k, v in pub_api.items():
    #     print(f'ZZZ === API: {k} : {v}\n')
    #
    # # build two ASTs for comparison
    # ast1 = AST(path_to_ast_files1)
    # # print(f'ZZZ === AST1\n{ast1}\n')
    # ast2 = AST(path_to_ast_files2)
    # # print(f'ZZZ === AST2\n{ast2}\n')
    #
    # # find modified methods
    # modified_methods_ids = set()
    # methods1 = ast1.find_methods()
    # print(f'ZZZ === methods1 : {len(methods1)}\n')
    # methods2 = ast2.find_methods()
    # print(f'ZZZ === methods2 : {len(methods2)}\n')
    # for m in methods1:
    #     if m not in methods2:
    #         print(f'ZZZ === modified method : {m}\n')
    #         modified_methods_ids.add(m.uid)
    # print(f'ZZZ === modified_methods_ids : {modified_methods_ids}\n')

    # # checks is public API affected and get linked fuzzers
    # for api, fuzzers in pub_api.items():
    #     print(f'ZZZ === CHECK METHOD: {api}')
    #     if is_method_affected(api, methods1, modified_methods_ids):
    #         print(f'ZZZ === METHOD AFFECTED: {api}')
    #         res.update(fuzzers)
    #     else:
    #         print(f'ZZZ === METHOD NOT AFFECTED: {api}')

    # return res



