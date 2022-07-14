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
    method_nodes = ['FunctionDecl', 'CXXConstructorDecl', 'CXXDestructorDecl', 'CXXMethodDecl', 'FunctionTemplateDecl']
    # 'CXXCtorInitializer'

    # keys that are needed to compare nodes
    used_node_keys = ['id', 'kind', 'name', 'mangledName', 'isUsed', 'virtual', 'type', 'valueCategory', 'value',
                      'opcode', 'castKind', 'isReferenced', 'referencedDecl', 'referencedMemberDecl', 'inner']

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
    def __init__(self, report_file_pathname: str, path_to_ast_files1: str, path_to_ast_files2: str):
        # find public APIs (linked to fuzzers)
        self._public_api = AffectedFuzzersFinder.__public_api(report_file_pathname)
        for k, v in self._public_api.items():
            print(f'ZZZ === API: {k} : {v}\n')

        # build ASTs and find existing methods
        methods1 = AST(path_to_ast_files1).find_methods()
        print(f'ZZZ === _existing_methods1 : {len(methods1)}\n')
        methods2 = AST(path_to_ast_files2).find_methods()
        print(f'ZZZ === _existing_methods2 : {len(methods2)}\n')

        # find modified methods
        self._modified_methods_ids = AffectedFuzzersFinder.__find_modified_methods_ids(methods1, methods2)
        print(f'ZZZ === modified_methods_ids : {self._modified_methods_ids}\n')

        self._existing_methods_by_id = dict()
        self._existing_methods_by_name = dict()
        for m in methods1:
            self._existing_methods_by_id.setdefault(m.uid, []).append(m)
            self._existing_methods_by_name.setdefault(m.display_name + m.mangled_name, []).append(m)

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
        return self.__is_nodes_affected({n.uid for n in self._existing_methods_by_name[method_name + method_name]})

    def __is_nodes_affected(self, nodes_ids: set, stack: set = set()) -> bool:
        for nid in nodes_ids:
            print(f'ZZZ ====== CHECK NODE: {nid}')

            if nid in stack:
                print(f'ZZZ ====== CHECK NODE: {nid} -> SKIP')
                continue

            if self._checked_nodes.get(nid, None) is None:
                stack.add(nid)
                self._checked_nodes[nid] = self.__is_node_affected(nid, stack)
                stack.remove(nid)
            if self._checked_nodes.get(nid, False):
                print(f'ZZZ ====== CHECK NODE: {nid} -> AFFECTED')
                return True
        return False

    def __is_node_affected(self, node_id: str, stack: set) -> bool:
        for method in self._existing_methods_by_id.get(node_id, []):
            if method.display_name == '' or method.mangled_name == '':
                continue
            for node in self._existing_methods_by_name.get(method.display_name + method.mangled_name, []):
                if node.uid in self._modified_methods_ids:
                    return True
                if self.__is_nodes_affected(node.find_referenced_methods(), stack):
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
