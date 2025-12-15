sample.cpp
   │
   ▼
[libclang] 解析 C++ 源码
   │  (Index.parse -> TranslationUnit)
   ▼
 顶层 AST 遍历
 (FUNCTION_DECL 节点)
   │
   ├─> emit_function
   │     ├─> map_cxx_type_to_carbon    （类型映射）
   │     ├─> 形参处理 (PARM_DECL)
   │     └─> emit_compound_stmt (函数体)
   │             └─> emit_stmt
   │                   ├─ DECL_STMT / VAR_DECL → emit_var_decl_from_cursor → emit_expr
   │                   ├─ RETURN_STMT → emit_expr
   │                   └─ EXPR_STMT   → emit_expr
   │
   ▼
 多个 Carbon 函数源码
   │
   ▼
 拼接字符串 → 写入 *.carbon 文件


 | C++ 语言特性  | Clang AST 节点      
| --------- | ----------------- |
| 函数定义      | `FUNCTION_DECL`   | 
| 形参        | `PARM_DECL`       | 
| 返回类型      | `result_type`     | 
| 局部变量      | `VAR_DECL`        | 
| 声明语句      | `DECL_STMT`       | 
| return 语句 | `RETURN_STMT`     | 
| 二元运算      | `BINARY_OPERATOR` | 
| 变量引用      | `DECL_REF_EXPR`   | 
| 整数常量      | `INTEGER_LITERAL` | 
| 函数调用      | `CALL_EXPR`       | 
| 语句块       | `COMPOUND_STMT`   | 

