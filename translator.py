import sys
import clang.cindex as cl

# M1/M2/M3 mac 基本都是这个路径：
cl.Config.set_library_file("/opt/homebrew/opt/llvm/lib/libclang.dylib")

# 简单的类型映射：C++ -> Carbon
def map_cxx_type_to_carbon(cxx_type: str) -> str:
    # demo：全部粗暴映射为 i32，后面你可以细化
    if cxx_type in ("int", "signed int", "long", "short"):
        return "i32"
    if cxx_type in ("unsigned int", "unsigned"):
        return "u32"
    if cxx_type == "bool":
        return "bool"
    # 兜底映射
    return "auto"


def get_source_text(node) -> str:
    """把某个 AST 节点下的 token 拼成源码片段（简单粗暴版）。"""
    tokens = list(node.get_tokens())
    return " ".join(t.spelling for t in tokens)


def emit_expr(node) -> str:
    """根据 AST 节点生成 Carbon 表达式（极简版，只处理常见几种）。"""
    kind = node.kind

    # 变量引用
    if kind == cl.CursorKind.DECL_REF_EXPR:
        return node.spelling

    # 字面量（整数）
    if kind == cl.CursorKind.INTEGER_LITERAL:
        # 对于 literal，直接用 token 文本
        return get_source_text(node)

    # 二元运算：a + b / a * b 等
    if kind == cl.CursorKind.BINARY_OPERATOR:
        # 简单起见：直接用 token 拼接，实际工程可以改成递归解析左右子树
        return get_source_text(node)

    # 一元运算、函数调用等，可以按需要扩展
    if kind == cl.CursorKind.CALL_EXPR:
        return get_source_text(node)

    # 兜底：直接输出 token 文本
    return get_source_text(node)


def emit_var_decl_from_cursor(node, indent: int = 0) -> str:
    """从 VAR_DECL 节点生成 Carbon 变量声明。"""
    ind = "    " * indent
    var_name = node.spelling
    var_type = map_cxx_type_to_carbon(node.type.spelling)
    init_expr = None
    for child in node.get_children():
        init_expr = emit_expr(child)
    if init_expr is None:
        return f"{ind}var {var_name}: {var_type};"
    else:
        return f"{ind}var {var_name}: {var_type} = {init_expr};"


def emit_stmt(node, indent: int = 0) -> list[str]:
    """根据语句节点生成一到多行 Carbon 代码（返回 list）。"""
    ind = "    " * indent
    kind = node.kind
    lines: list[str] = []

    # 1. 声明语句：int x = 1; int y = 2; 这一类
    if kind == cl.CursorKind.DECL_STMT:
        # 里面通常包着一个或多个 VAR_DECL
        for child in node.get_children():
            if child.kind == cl.CursorKind.VAR_DECL:
                lines.append(emit_var_decl_from_cursor(child, indent))
            else:
                # 其他声明，也可以递归处理
                lines.extend(emit_stmt(child, indent))
        return lines

    # 2. 单个 VAR_DECL（有些场景可能直接出现）
    if kind == cl.CursorKind.VAR_DECL:
        lines.append(emit_var_decl_from_cursor(node, indent))
        return lines

    # 3. return 语句
    if kind == cl.CursorKind.RETURN_STMT:
        children = list(node.get_children())
        if children:
            ret_expr = emit_expr(children[0])
            lines.append(f"{ind}return {ret_expr};")
        else:
            lines.append(f"{ind}return;")
        return lines

    # 4. 表达式语句：形如 `z = add(x, y);`
    if kind == cl.CursorKind.EXPR_STMT:
        # 取唯一子节点作为表达式
        children = list(node.get_children())
        if children:
            expr = emit_expr(children[0])
            lines.append(f"{ind}{expr};")
        return lines

    # 5. 直接把某些表达式当语句（兜底）
    if kind in (cl.CursorKind.BINARY_OPERATOR, cl.CursorKind.CALL_EXPR):
        expr = emit_expr(node)
        lines.append(f"{ind}{expr};")
        return lines

    # 6. 复合语句（代码块），由 emit_compound_stmt 统一处理，这里不直接输出
    if kind == cl.CursorKind.COMPOUND_STMT:
        return []

    # 7. 其他暂不支持的语句
    src = get_source_text(node)
    lines.append(f"{ind}// [UNSUPPORTED STMT] {src}")
    return lines


def emit_compound_stmt(node, indent: int = 0) -> str:
    """处理 { ... } 代码块。"""
    lines: list[str] = []
    for child in node.get_children():
        child_lines = emit_stmt(child, indent)
        for line in child_lines:
            if line.strip():
                lines.append(line)
    return "\n".join(lines)



def emit_function(node) -> str:
    """把一个 C++ 函数定义翻译成 Carbon fn。"""
    func_name = node.spelling
    ret_type = map_cxx_type_to_carbon(node.result_type.spelling)

    # 处理参数
    params = []
    for c in node.get_children():
        if c.kind == cl.CursorKind.PARM_DECL:
            p_name = c.spelling
            p_type = map_cxx_type_to_carbon(c.type.spelling)
            params.append(f"{p_name}: {p_type}")

    param_str = ", ".join(params)

    # 查找函数体
    body = None
    for c in node.get_children():
        if c.kind == cl.CursorKind.COMPOUND_STMT:
            body = c
            break

    header = f"fn {func_name}({param_str}) -> {ret_type} " + "{"
    if body is None:
        # 声明而非定义
        return header + " // no body }"

    body_str = emit_compound_stmt(body, indent=1)
    footer = "}"

    return header + "\n" + body_str + "\n" + footer


def translate_cpp_to_carbon(filename: str) -> str:
    """主入口：解析一个 C++ 文件，输出 Carbon 源码字符串。"""
    index = cl.Index.create()
    tu = index.parse(filename, args=["-std=c++14"])

    carbon_funcs = []

    for cursor in tu.cursor.get_children():
        # 只处理最外层的函数定义
        if cursor.kind == cl.CursorKind.FUNCTION_DECL and cursor.is_definition():
            carbon_code = emit_function(cursor)
            carbon_funcs.append(carbon_code)

    return "\n\n".join(carbon_funcs)


def main():
    if len(sys.argv) < 2:
        print("Usage: python translator.py <source.cpp>")
        sys.exit(1)

    src_file = sys.argv[1]
    carbon_code = translate_cpp_to_carbon(src_file)

    out_file = "output.carbon"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(carbon_code)

    print(f"Carbon code written to: {out_file}")



if __name__ == "__main__":
    main()
