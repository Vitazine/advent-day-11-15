import json

def export_events(ledger,destination):
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(ledger.events(),ensure_ascii=False,indent=2))
