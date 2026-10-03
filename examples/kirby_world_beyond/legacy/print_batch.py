import json, sys

with open("all_segments_raw.json", "r", encoding="utf-8") as f:
    data = json.load(f)

start_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 1
end_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 70

with open("batch_view.txt", "w", encoding="utf-8") as out:
    for item in data:
        if start_idx <= item["id"] <= end_idx:
            out.write(f"[{item['id']}] {item['time']} : {item['ja_raw']}\n")
print(f"Wrote {start_idx} to {end_idx}")