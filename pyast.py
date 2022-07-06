#!/usr/bin/env python


import os
import re
import json


class ASTException(Exception):
    pass


    # def __init__(self, file_pathname: str, node: dict):
    #     self.file_pathname = file_pathname
    #     self.id = ''
    #     self.params = {}
    #     self.leaves = []
    #
    #     for k, v in node.items():
    #         if k in ASTNode.used_node_keys:
    #             if k == 'id':
    #                 self.id = v
    #             elif k == 'type':
    #                 self.params['type'] = v.get('qualType', '')
    #             elif k == 'referencedDecl':
    #                 self.params['ref'] = {'kind': v.get('kind', ''), 'name': v.get('name', ''),
    #                                       'type': v.get('type', {}).get('qualType', '')}
    #             elif k == 'inner':
    #                 self.leaves = ASTNode.__parse(file_pathname, v)
    #             else:
    #                 self.params[k] = v
    #         # elif k not in ASTNode.forbidden_node_keys:
    #         #     print(f'ZZZ ========================= {k} : {v}')
    #
    #     # some tuning
    #     # 1. in some cases self.params['type'] may be a string containing the path with line/col numbers, for ex:
    #     # '(lambda at /home/abuild/rpmbuild/BUILD/capi-context-1.0.6/src/trigger/CustomTemplate.cpp:295:3)'
    #     # just remove the line/col numbers
    #     t = self.params.get('type', None)
    #     if t:
    #         self.params['type'] = re.sub(r':[0-9]+:[0-9]+', '', t)
    #     # 2. the same for self.params['ref']['type']
    #     t = self.params.get('ref', {}).get('type', None)
    #     if t:
    #         self.params['ref']['type'] = re.sub(r':[0-9]+:[0-9]+', '', t)
    #     # 3. can't explain but it's necessary
    #     k = self.params.get('kind', '')
    #     if (k == 'IntegerLiteral' or k == 'StringLiteral') and \
    #             self.params.get('valueCategory', '') == 'rvalue' and self.params.get('value', None):
    #         self.params['value'] = ''


# referencedDecl
# foundReferencedDecl
# referencedMemberDecl
# decl

class ASTNode:
    used_node_keys = ['id', 'kind', 'name', 'mangledName', 'isUsed', 'type', 'valueCategory', 'value', 'opcode',
                      'castKind', 'isReferenced', 'referencedDecl', 'inner']
    forbidden_node_keys = ['id', 'loc', 'range']
    # access, storageClass, inline,

    def __init__(self, file_pathname: str, node: dict):
        self.file_pathname = file_pathname
        self.id = ''
        self.params = {}
        self.leaves = []

        for k, v in node.items():
            if k in ASTNode.used_node_keys:
                if k == 'id':
                    self.id = v
                elif k == 'type':
                    self.params['type'] = v.get('qualType', '')
                elif k == 'referencedDecl':
                    self.params['referencedDecl'] = ASTNode(file_pathname, v)
                elif k == 'inner':
                    self.leaves = ASTNode.__parse(file_pathname, v)
                else:
                    self.params[k] = v
            # elif k not in ASTNode.forbidden_node_keys:
            #     print(f'ZZZ ========================= {k} : {v}')

        # some tuning
        # 1. in some cases self.params['type'] may be a string containing the path with line/col numbers, for ex:
        # '(lambda at /home/abuild/rpmbuild/BUILD/capi-context-1.0.6/src/trigger/CustomTemplate.cpp:295:3)'
        # just remove the line/col numbers
        t = self.params.get('type', None)
        if t:
            self.params['type'] = re.sub(r':[0-9]+:[0-9]+', '', t)
        # 2. can't explain
        k = self.params.get('kind', '')
        if (k == 'IntegerLiteral' or k == 'StringLiteral') and \
                self.params.get('valueCategory', '') == 'rvalue' and self.params.get('value', None):
            self.params['value'] = ''

    def __str__(self):
        return self.__print()

    def __eq__(self, other):
        if not isinstance(other, ASTNode):
            return False

        # check common fields
        if self.params != other.params:
            return False

        # checks for child items
        if len(self.leaves) != len(other.leaves):
            return False
        for node in self.leaves:
            if node not in other.leaves:
                return False

        return True

    def find_methods(self, display_name: str = None, mangled_name: str = None) -> list:
        res = []

        kind = self.params.get('kind', '')
        if kind in ['FunctionDecl', 'CXXMethodDecl']:
            match = True
            if display_name and display_name != self.params.get('name', ''):
                match = False
            if match and mangled_name and mangled_name != self.params.get('mangledName', ''):
                match = False
            if match:
                res.append(self)
        elif kind in ['TranslationUnitDecl', 'NamespaceDecl']:
            # CXCursor_TranslationUnit -> TranslationUnitDecl
            # CXCursor_ClassDecl
            # CXCursor_Namespace -> NamespaceDecl
            # CXCursor_StmtExpr -> StmtExpr
            for leaf in self.leaves:
                res.extend(leaf.find_methods(display_name, mangled_name))

        return res

    @staticmethod
    def __parse(file_pathname: str, nodes: list):
        res = []
        for node in nodes:
            res.append(ASTNode(file_pathname, node))
        return res

    def __print(self, prefix='|'):
        res = f'{prefix} ASTNode(id: {self.id}, '
        for k, v in self.params.items():
            res += f'{k} : {v}, '
        res += ')\n'
        for leaf in self.leaves:
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

    def find_methods(self, display_name: str = None, mangled_name:str = None) -> list:
        return self.root.find_methods(display_name, mangled_name)


class AST:
    def __init__(self, project_pathname: str):
        self.project_pathname = project_pathname
        self.tu = []
        for ast in AST.__ast_files(project_pathname):
            with open(ast) as f:
                try:
                    self.tu.append(ASTTu(ast, json.load(f)))
                except ASTException as e:
                    print(f"Can't parse ast {ast} : {e}")

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
            res.extend([os.path.join(root, f) for f in files if re.search(r'.*\.ast$', f)])
        return res



def main():
    ast1 = AST('/home/iuriim/tmp/qwe/context/1')
    # print(f'============= AST1\n{ast1}')
    ast2 = AST('/home/iuriim/tmp/qwe/context/2')
    # # print(f'============= AST1\n{ast2}')

    nodes1 = ast1.find_methods()
    print(f'ZZZ =========== nodes1 : {len(nodes1)}\n')
    nodes2 = ast2.find_methods()
    print(f'ZZZ =========== nodes2 : {len(nodes2)}\n')
    for node1 in nodes1:
        if node1 not in nodes2:
            print(f'ZZZ ======================= {node1}')


    # nodes1 = ast1.find_methods(display_name='__is_valid_pkg_id')
    # print(f'ZZZ =========== nodes1 : {len(nodes1)}\n')
    # # for n1 in nodes1:
    # #     print(f'ZZZ =========== n1 : \n{n1}\n')
    # # print(f'ZZZ =========== node1 : \n{nodes1[0]}\n')
    # nodes2 = ast2.find_methods(display_name='__is_valid_pkg_id')
    # print(f'ZZZ =========== nodes2 : {len(nodes2)}\n')
    # # for n2 in nodes2:
    # #     print(f'ZZZ =========== n2 : \n{n2}\n')
    # # print(f'ZZZ =========== node2 : \n{nodes2[0]}\n')
    # # for node1 in nodes1:
    # #     if node1 not in nodes2:
    # #         print(f'ZZZ ======================= \n{node1}\n')






if __name__ == '__main__':
    main()
