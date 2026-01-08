from modelscope.hub.api import HubApi
import sys
print("Starting search...")
api = HubApi()
found_any = False
for group in ['iic', 'damo']:
    print(f"Checking group: {group}...")
    try:
        res = api.list_models(owner_or_group=group)
        if not isinstance(res, dict):
             print(f"  Unexpected response type for {group}: {type(res)}")
             continue
        models = res.get('Models', [])
        print(f"  Found {len(models)} models.")
        for m in models:
             m_str = str(m).lower()
             if 'mossformer' in m_str:
                 print(f"  MATCH: ID={m.get('Id')} | Name={m.get('Name')}")
                 found_any = True
    except Exception as e:
        print(f"  Error checking {group}: {e}")

if not found_any:
    print("No MossFormer models found in iic or damo groups.")
