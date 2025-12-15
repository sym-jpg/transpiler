from translator.backend.carbon_emitter import CarbonEmitter
from translator.frontend.demo_ir import *

from translator.backend.carbon_rules import DEFAULT_CARBON_RULES
from translator.backend.carbon_emitter import CarbonEmitter

emitter = CarbonEmitter(rules=DEFAULT_CARBON_RULES)
carbon_code = emitter.emit_function(build_demo_ir())
print(carbon_code)

