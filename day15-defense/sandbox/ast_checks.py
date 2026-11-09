"""Explicit Python security checks supplement general-purpose Bandit rules."""
import ast

def scan(source):
    reasons=set()
    try:tree=ast.parse(source)
    except (SyntaxError,ValueError,RecursionError):return {'SYNTAX_INVALID'}
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):continue
        function=node.func
        name=function.id if isinstance(function,ast.Name) else (function.attr if isinstance(function,ast.Attribute) else '')
        if name in ('eval','exec','system','popen','_exit'):reasons.add('DYNAMIC_EXECUTION')
        for kw in node.keywords:
            if isinstance(kw.value,ast.Constant):
                if kw.arg=='verify' and kw.value.value is False:reasons.add('TLS_DISABLED')
                if kw.arg=='shell' and kw.value.value is True:reasons.add('SHELL_EXECUTION')
        if name in ('debug','info','warning','error','critical','exception','log'):
            for argument in node.args:
                for value in ast.walk(argument):
                    if isinstance(value,ast.Attribute) and value.attr in ('headers','environ'):reasons.add('SENSITIVE_LOGGING')
                    if isinstance(value,ast.Name) and value.id.lower() in ('token','password','secret','api_key'):reasons.add('SENSITIVE_LOGGING')
    return reasons
