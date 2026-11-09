from pathlib import Path
p=Path(__file__).resolve().parents[1]/'tests/test_in_place_packaging.py';s=p.read_text()
old="  options={k.arg:ast.literal_eval(k.value) for k in exe.keywords}"
new="  options={k.arg:ast.literal_eval(k.value) for k in exe.keywords if k.arg in {'exclude_binaries','console'}}\n  icon=next(k.value for k in exe.keywords if k.arg=='icon');self.assertIn('canonical',ast.unparse(icon))"
assert old in s;s=s.replace(old,new);p.write_text(s,encoding='utf-8');print('AST check retains binary/windowed assertions and separately checks canonical icon path.')
