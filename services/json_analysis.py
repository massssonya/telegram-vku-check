import os
import tempfile
import pandas as pd
import json
import shutil
from telegram import error
from collections import defaultdict
from typing import Dict, List, Any, Set, Optional


class JSONProcessor:
    """Класс для обработки JSON файлов и анализа структуры экранов."""
    
    def __init__(self):
        self.screens: Dict[str, Dict] = {}
        self.edges = defaultdict(list)
        self.adj: Dict[str, List[str]] = {}
        self.paths: List[Dict] = []
        self.MAX_PATHS = 10000

    async def process_json_file(self, update, context, document):
        """Основной метод обработки JSON файла."""
        processing_message = await update.message.reply_text("Получен JSON. Обработка...")
        temp_dir = None

        try:
            # Загрузка и парсинг файла
            json_data = await self._download_and_parse_json(context, document)
            
            # Анализ структуры
            self._analyze_structure(json_data)
            
            # Диагностика экранов
            diagnostics = self._generate_diagnostics()
            
            # Поиск путей
            start_screen = self._find_start_screen(json_data)
            if start_screen:
                self._find_paths(start_screen)
            
            # Поиск недостижимых экранов
            unreachable_screens = self._find_unreachable_screens()
            
            # Создание отчетов
            temp_dir = await self._generate_reports(
                diagnostics, unreachable_screens, update, context
            )
            
            await self._cleanup(processing_message)

        except json.JSONDecodeError:
            await update.message.reply_text("Ошибка: не удалось распарсить JSON.")
        except error.TelegramError as e:
            await update.message.reply_text(f"Ошибка Telegram API: {e}")
        except Exception as e:
            await update.message.reply_text(f"Ошибка при обработке: {e}")
        finally:
            self._cleanup_temp_dir(temp_dir)

    async def _download_and_parse_json(self, context, document) -> Dict:
        """Загружает и парсит JSON файл."""
        file_id = document.file_id
        new_file = await context.bot.get_file(file_id)
        file_content = await new_file.download_as_bytearray()
        json_data = file_content.decode('utf-8')
        return json.loads(json_data)

    def _analyze_structure(self, json_data: Dict):
        """Анализирует структуру JSON и строит граф переходов."""
        self.screens = {s["id"]: s for s in json_data.get("screens", [])}
        
        screen_rules = json_data.get("screenRules", {})
        cycled_screen_rules = json_data.get("cycledScreenRules", {})
        
        self._collect_edges(screen_rules, "screenRules")
        self._collect_edges(cycled_screen_rules, "cycledScreenRules")
        
        self.adj = {
            screen_id: sorted({edge["next"] for edge in edges if edge["next"]})
            for screen_id, edges in self.edges.items()
        }

    def _collect_edges(self, rules_block: Dict, source_label: str):
        """Собирает информацию о переходах между экранами."""
        for screen_id, rules in rules_block.items():
            if not isinstance(rules, list):
                continue
                
            for rule in rules:
                next_displays = self._extract_next_displays(rule.get("nextDisplay"))
                conditions_count = self._count_conditions(rule)
                
                if not next_displays:
                    self._add_edge(screen_id, None, conditions_count, source_label, rule)
                else:
                    for next_display in next_displays:
                        self._add_edge(screen_id, next_display, conditions_count, source_label, rule)

    def _extract_next_displays(self, next_display) -> List[str]:
        """Извлекает список следующих экранов из правила."""
        if isinstance(next_display, list):
            return self._extract_from_list(next_display)
        elif isinstance(next_display, str):
            return [next_display]
        return []

    def _extract_from_list(self, items: List) -> List[str]:
        """Извлекает идентификаторы экранов из списка."""
        next_displays = []
        for item in items:
            if isinstance(item, str):
                next_displays.append(item)
            elif isinstance(item, dict):
                next_displays.extend(self._extract_from_dict(item))
        return next_displays

    def _extract_from_dict(self, item: Dict) -> List[str]:
        """Извлекает идентификатор экрана из словаря."""
        for key in ("id", "screenId", "next", "displayId", "nextDisplay"):
            if key in item and isinstance(item[key], str):
                return [item[key]]
        return []

    def _count_conditions(self, rule: Dict) -> int:
        """Подсчитывает количество условий в правиле."""
        conditions = rule.get("conditions", [])
        return len(conditions) if isinstance(conditions, list) else 0

    def _add_edge(self, screen_id: str, next_screen: Optional[str], 
                 conditions_count: int, source_label: str, rule: Dict):
        """Добавляет переход в список edges."""
        self.edges[screen_id].append({
            "next": next_screen,
            "conditions_count": conditions_count,
            "source": source_label,
            "raw_rule": rule
        })

    def _generate_diagnostics(self) -> pd.DataFrame:
        """Генерирует диагностическую информацию по экранам."""
        diagnostics = []
        
        for screen_id, screen in self.screens.items():
            rules = self.edges.get(screen_id, [])
            issues = self._analyze_screen_issues(screen, rules)
            
            diagnostics.append({
                "screen": screen_id,
                "name": screen.get("name"),
                "terminal": bool(screen.get("isTerminal")),
                "has_rules": len(rules) > 0,
                "out_degree": len({e["next"] for e in rules if e["next"]}),
                "distinct_nexts": ", ".join(sorted({e["next"] for e in rules if e["next"]})),
                "unconditional_transitions": sum(1 for e in rules if e["conditions_count"] == 0 and e["next"]),
                "rules_without_next": sum(1 for e in rules if e["next"] is None),
                "issues": "; ".join(issues)
            })
        
        return pd.DataFrame(diagnostics).sort_values(["issues", "screen"]).reset_index(drop=True)

    def _analyze_screen_issues(self, screen: Dict, rules: List[Dict]) -> List[str]:
        """Анализирует проблемы экрана."""
        issues = []
        terminal = bool(screen.get("isTerminal"))
        out_nexts_count = len({e["next"] for e in rules if e["next"]})
        unconditional_count = sum(1 for e in rules if e["conditions_count"] == 0 and e["next"])
        no_next_rules = sum(1 for e in rules if e["next"] is None)

        if out_nexts_count == 0 and not terminal:
            issues.append("DEAD_END(no outgoing rules & not terminal)")
        if unconditional_count > 1:
            issues.append(f"AMBIGUOUS(multiple unconditional transitions={unconditional_count})")
        if no_next_rules > 0 and not terminal:
            issues.append(f"NO_NEXT_RULES({no_next_rules})")
            
        return issues

    def _find_start_screen(self, json_data: Dict) -> Optional[str]:
        """Находит начальный экран."""
        init_screen = json_data.get("init")
        if init_screen:
            return init_screen
            
        for screen_id, screen in self.screens.items():
            if screen.get("isFirstScreen"):
                return screen_id
                
        return None

    def _find_paths(self, start_screen: str):
        """Находит все возможные пути через граф экранов."""
        self._dfs(start_screen, [])

    def _dfs(self, current: str, path: List[str]):
        """Рекурсивный поиск в глубину для нахождения путей."""
        if len(self.paths) >= self.MAX_PATHS:
            return
            
        if current in path:
            cycle_path = path + [current]
            self.paths.append({"path": cycle_path, "status": "CYCLE"})
            return
            
        new_path = path + [current]
        next_screens = self.adj.get(current, [])
        terminal = bool(self.screens.get(current, {}).get("isTerminal"))
        
        if not next_screens:
            status = "TERMINAL" if terminal else "DEAD_END"
            self.paths.append({"path": new_path, "status": status})
            return
            
        for next_screen in next_screens:
            self._dfs(next_screen, new_path)

    def _find_unreachable_screens(self) -> pd.DataFrame:
        """Находит недостижимые экраны."""
        reachable = set()
        for path_info in self.paths:
            reachable.update(path_info["path"])
            
        unreachable = sorted(set(self.screens.keys()) - reachable)
        return pd.DataFrame([
            {"screen": screen_id, "name": self.screens[screen_id].get("name")} 
            for screen_id in unreachable
        ])

    async def _generate_reports(self, diagnostics: pd.DataFrame, 
                              unreachable_screens: pd.DataFrame,
                              update, context) -> str:
        """Генерирует и отправляет отчеты."""
        temp_dir = tempfile.mkdtemp()
        
        # Создание путей к файлам
        file_paths = {
            'diagnostics': os.path.join(temp_dir, 'Диагностика по экранам.xlsx'),
            'paths': os.path.join(temp_dir, 'Сценарии прохождения.xlsx'),
            'unreachable': os.path.join(temp_dir, 'Недостижимые экраны.xlsx')
        }
        
        # Сохранение в Excel
        diagnostics.to_excel(file_paths['diagnostics'], index=False)
        
        paths_df = pd.DataFrame([
            {"length": len(p["path"]), "status": p["status"], "path": " -> ".join(p["path"])}
            for p in self.paths
        ]).sort_values(["status", "length"]).reset_index(drop=True)
        paths_df.to_excel(file_paths['paths'], index=False)
        
        unreachable_screens.to_excel(file_paths['unreachable'], index=False)
        
        # Отправка файлов
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="Анализ завершён. Вот результаты:"
        )
        
        for file_type, filename in [
            ('diagnostics', 'Диагностика.xlsx'),
            ('paths', 'Сценарии.xlsx'),
            ('unreachable', 'Недостижимые.xlsx')
        ]:
            with open(file_paths[file_type], 'rb') as f:
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=filename
                )
        
        return temp_dir

    async def _cleanup(self, processing_message):
        """Удаляет сообщение о обработке."""
        await context.bot.delete_message(
            chat_id=processing_message.chat_id,
            message_id=processing_message.message_id
        )

    def _cleanup_temp_dir(self, temp_dir: Optional[str]):
        """Удаляет временную директорию."""
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)


# Функция для обратной совместимости
async def process_json_file(update, context, document):
    """Старая функция для обратной совместимости."""
    processor = JSONProcessor()
    await processor.process_json_file(update, context, document)