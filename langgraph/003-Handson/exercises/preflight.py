import json
import prototype_01 as p

# 1) validate を、前回の案で動かす(LLM なし)
d = json.load(open("month_draft.json", encoding="utf-8"))["assignments"]
state = {"draft_store_shift": d, "llm_all_staff": p.llm_all_staff,
         "return_count": 1, "upper_limit": 3, "result": "", "problems": []}
out = p.validate(state)
print("validate の結果:", out["result"], "/ 問題の件数:", len(out.get("problems", [])))

# 2) auto_draft が作る質問文を見る(LLM のかわりに、偽物を差し込む)
class Fake:
    def invoke(self, prompt):
        i = prompt.find("【資格のルール")
        j = prompt.find("【スタッフのデータ")
        print("--- 質問文の途中(資格のルール〜スタッフのデータの前) ---")
        print(prompt[i:j])
        raise SystemExit

p.llm = Fake()
p.auto_draft({"llm_all_staff": p.llm_all_staff, "return_count": 0,
              "problems": ["テスト問題1", "テスト問題2"]})