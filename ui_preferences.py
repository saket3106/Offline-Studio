"""Strict presentation preferences; never mutate inference settings or load models."""
DEFAULTS = {"theme":"dark", "ui_accent":"neutral", "ui_density":"comfortable", "ui_chat_font_size":15, "ui_content_width":860,
 "ui_sidebar":"expanded", "ui_inspector":"contextual", "ui_motion":"system", "ui_message_details":"minimal", "ui_code_wrap":False}
CHOICES = {"theme":("dark","light"), "ui_accent":("neutral","blue","sage"), "ui_density":("comfortable","compact"), "ui_sidebar":("expanded","collapsed"),
 "ui_inspector":("contextual","manual"), "ui_motion":("system","reduced"), "ui_message_details":("minimal","detailed")}
RANGES = {"ui_chat_font_size":(13,20), "ui_content_width":(640,1120)}
def validate(values):
 if type(values) is not dict or not values or set(values)-set(DEFAULTS): raise ValueError("Unknown or empty appearance preference object")
 result={}
 for key,value in values.items():
  if key in CHOICES and (type(value) is not str or value not in CHOICES[key]): raise ValueError("Unsupported "+key)
  if key in RANGES and (type(value) is not int or not RANGES[key][0]<=value<=RANGES[key][1]): raise ValueError("Out of range "+key)
  if key=='ui_code_wrap' and type(value) is not bool: raise ValueError("Code wrap must be boolean")
  result[key]=value
 return result

def read(config):
 result=dict(DEFAULTS)
 for key in DEFAULTS:
  try: result.update(validate({key:config[key]}))
  except (ValueError,KeyError): pass
 return result
