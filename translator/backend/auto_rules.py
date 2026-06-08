# translator/backend/auto_rules.py

class AutoRuleManager:
    def __init__(self, base_rules, synthesizer):
        self.rules = base_rules
        self.synthesizer = synthesizer

    def emit_expr(self, emitter, expr):
        try:
            fn = self.rules.expr(expr)
            return fn(emitter, expr)
        except NotImplementedError as e:
            patch = self.synthesizer.synthesize_expr_rule(expr, emitter)
            self.rules = self.rules.overlay(patch)
            return self.rules.expr(expr)(emitter, expr)

    def emit_stmt(self, emitter, stmt, indent):
        try:
            fn = self.rules.stmt(stmt)
            return fn(emitter, stmt, indent)
        except NotImplementedError:
            patch = self.synthesizer.synthesize_stmt_rule(stmt, emitter)
            self.rules = self.rules.overlay(patch)
            return self.rules.stmt(stmt)(emitter, stmt, indent)
            