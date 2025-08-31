import os
import tempfile
import pandas as pd
import json
import shutil
from telegram import error

async def process_json_file(update, context, document):
    processing_message = await update.message.reply_text("Получен JSON. Обработка...")

    file_id = document.file_id
    temp_dir = None
    try:
        new_file = await context.bot.get_file(file_id)
        file_content = await new_file.download_as_bytearray()
        json_data = file_content.decode('utf-8')
        parsed_json = json.loads(json_data)

        # Вся твоя логика анализа JSON ↓↓↓
        from collections import defaultdict

        screens = {s["id"]: s for s in parsed_json.get("screens", [])}
        init_screen = parsed_json.get("init")

        screenRules = parsed_json.get("screenRules", {})
        cycledScreenRules = parsed_json.get("cycledScreenRules", {})

        def collect_edges(block: dict, source_label: str, edges: dict):
            for screen_id, rules in block.items():
                if not isinstance(rules, list):
                    continue
                for rule in rules:
                    nxt = rule.get("nextDisplay")
                    nexts = []
                    if isinstance(nxt, list):
                        for item in nxt:
                            if isinstance(item, str):
                                nexts.append(item)
                            elif isinstance(item, dict):
                                for k in ("id", "screenId", "next", "displayId", "nextDisplay"):
                                    if k in item and isinstance(item[k], str):
                                        nexts.append(item[k])
                                        break
                    elif isinstance(nxt, str):
                        nexts.append(nxt)
                    else:
                        nexts = []
                    conds_cnt = len(rule.get("conditions", [])) if isinstance(rule.get("conditions", []), list) else 0
                    if not nexts:
                        edges[screen_id].append({
                            "next": None,
                            "conditions_count": conds_cnt,
                            "source": source_label,
                            "raw_rule": rule
                        })
                    else:
                        for n in nexts:
                            edges[screen_id].append({
                                "next": n,
                                "conditions_count": conds_cnt,
                                "source": source_label,
                                "raw_rule": rule
                            })

        edges = defaultdict(list)
        collect_edges(screenRules, "screenRules", edges)
        collect_edges(cycledScreenRules, "cycledScreenRules", edges)

        adj = {sid: sorted({e["next"] for e in lst if e["next"]}) for sid, lst in edges.items()}

        diagnostics = []
        for sid, screen in screens.items():
            rules_for = edges.get(sid, [])
            out_nexts = sorted({e["next"] for e in rules_for if e["next"]})
            out_nexts_count = len(out_nexts)
            terminal = bool(screen.get("isTerminal"))
            unconditional_count = sum(1 for e in rules_for if e["conditions_count"] == 0 and e["next"])
            no_next_rules = sum(1 for e in rules_for if e["next"] is None)
            issues = []
            if out_nexts_count == 0 and not terminal:
                issues.append("DEAD_END(no outgoing rules & not terminal)")
            if unconditional_count > 1:
                issues.append(f"AMBIGUOUS(multiple unconditional transitions={unconditional_count})")
            if no_next_rules > 0 and not terminal:
                issues.append(f"NO_NEXT_RULES({no_next_rules})")
            diagnostics.append({
                "screen": sid,
                "name": screen.get("name"),
                "terminal": terminal,
                "has_rules": len(rules_for) > 0,
                "out_degree": out_nexts_count,
                "distinct_nexts": ", ".join(out_nexts),
                "unconditional_transitions": unconditional_count,
                "rules_without_next": no_next_rules,
                "issues": "; ".join(issues)
            })

        diag_df = pd.DataFrame(diagnostics).sort_values(["issues","screen"]).reset_index(drop=True)

        paths = []
        MAX_PATHS = 10000

        def dfs(current, path):
            if len(paths) >= MAX_PATHS:
                return
            if current in path:
                cycle_path = path + [current]
                paths.append({"path": cycle_path, "status": "CYCLE"})
                return
            path2 = path + [current]
            nexts = adj.get(current, [])
            terminal = bool(screens.get(current, {}).get("isTerminal"))
            if not nexts:
                status = "TERMINAL" if terminal else "DEAD_END"
                paths.append({"path": path2, "status": status})
                return
            for n in nexts:
                dfs(n, path2)

        start = init_screen if init_screen else next((s for s in screens if screens[s].get("isFirstScreen")), None)
        if start:
            dfs(start, [])

        paths_df = pd.DataFrame([
            {"length": len(p["path"]), "status": p["status"], "path": " -> ".join(p["path"])}
            for p in paths
        ]).sort_values(["status","length"]).reset_index(drop=True)

        reachable = set()
        for p in paths:
            reachable.update(p["path"])
        unreachable = sorted(set(screens.keys()) - reachable)
        unreach_df = pd.DataFrame([{"screen": sid, "name": screens[sid].get("name")} for sid in unreachable])

        temp_dir = tempfile.mkdtemp()
        diag_excel_path = os.path.join(temp_dir, 'Диагностика по экранам.xlsx')
        paths_excel_path = os.path.join(temp_dir, 'Сценарии прохождения.xlsx')
        unreach_excel_path = os.path.join(temp_dir, 'Недостижимые экраны.xlsx')

        diag_df.to_excel(diag_excel_path, index=False)
        paths_df.to_excel(paths_excel_path, index=False)
        unreach_df.to_excel(unreach_excel_path, index=False)

        await context.bot.send_message(chat_id=update.effective_chat.id, text="Анализ завершён. Вот результаты:")

        with open(diag_excel_path, 'rb') as f:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename='Диагностика.xlsx')

        with open(paths_excel_path, 'rb') as f:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename='Сценарии.xlsx')

        with open(unreach_excel_path, 'rb') as f:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename='Недостижимые.xlsx')

        await context.bot.delete_message(chat_id=processing_message.chat_id, message_id=processing_message.message_id)

    except json.JSONDecodeError:
        await update.message.reply_text("Ошибка: не удалось распарсить JSON.")
    except error.TelegramError as e:
        await update.message.reply_text(f"Ошибка Telegram API: {e}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке: {e}")
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
