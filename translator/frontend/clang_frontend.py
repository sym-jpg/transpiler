from clang import cindex
from clang.cindex import Cursor, CursorKind
from translator.frontend.clang_to_ir import *
from translator.frontend.clang_to_ir import lower_function
from translator.ir.typecheck import typecheck_function
from translator.backend.carbon_rules import DEFAULT_CARBON_RULES
from translator.backend.carbon_emitter import CarbonEmitter

cindex.Config.set_library_file(
    "/opt/homebrew/opt/llvm/lib/libclang.dylib"
)

def dump_ast(filename: str):
    index = cindex.Index.create()
    tu = index.parse(
        filename,
        args=["-std=c11"],
    )

    def visit(node, indent=0):
        print("  " * indent, node.kind, node.spelling, getattr(node.type, "spelling", ""))
        for c in node.get_children():
            visit(c, indent + 1)

    visit(tu.cursor)

    for c in tu.cursor.get_children():
        if c.kind == CursorKind.FUNCTION_DECL :
            fn = lower_function(c)
            #typecheck_function(fn)
            emitter = CarbonEmitter(rules=DEFAULT_CARBON_RULES)
            code = emitter.emit_function(fn)
            print("=== Carbon ===")
            print(code)


if __name__ == "__main__":
    dump_ast("dataset/test.c")
    

