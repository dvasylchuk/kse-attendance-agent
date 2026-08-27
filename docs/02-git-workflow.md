# Як працюємо з git — інструкція для команди

Троє людей, три треки, один репозиторій. Правила короткі, але виконуються без
винятків — інакше ми витратимо на мерж-конфлікти більше часу, ніж на код.

## Одноразове налаштування

```bash
gh auth login                          # GitHub CLI, авторизація через браузер
git clone https://github.com/dvasylchuk/kse-attendance-agent.git
cd kse-attendance-agent

python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env                   # заповнити OPENROUTER_API_KEY
python scripts/verify_mcp.py           # має вивести 5 інструментів
```

`.env` у `.gitignore`. Ключі в репозиторій не потрапляють — це окремий пункт
рубрики, за який знімають бали.

## Щоденний цикл

```bash
# 1. що вільно взяти
bash scripts/next_ticket.sh track:A-server

# 2. взяти тікет — бот призначить тебе і поставить status:in-progress
gh issue comment 12 --body "/take"

# 3. гілка від свіжого main
git switch main && git pull --ff-only
git switch -c a3-detect-schedule-conflicts-12

# 4. робота, дрібні коміти
git add -A && git commit -m "feat(mcp): detect calendar conflicts"

# 5. перевірка перед пушем
ruff check . && pytest -q && python scripts/verify_mcp.py

# 6. PR
git push -u origin HEAD
gh pr create --fill --body "Closes #12"

# 7. хтось із команди рев'ює і мерджить
gh pr review 15 --approve
gh pr merge 15 --squash --delete-branch --auto
```

Після мержу issue закривається автоматично (через `Closes #12`), а воркфлоу
`unblock-dependents` знімає `status:blocked` з тікетів, які на нього чекали, і
пише в них коментар. Це і є сигнал наступному, що можна починати.

## Статуси тікета

| Мітка | Що означає | Хто ставить |
|---|---|---|
| `status:ready` | вільний, залежності закриті | бот |
| `status:in-progress` | хтось узяв через `/take` | бот |
| `status:review` | відкрито PR | ставиш сам |
| `status:blocked` | чекає на інший тікет | бот |
| закрито | PR змерджено | автоматично |

Відпустити тікет, якщо не встигаєш: `gh issue comment 12 --body "/drop"`.

## Назви гілок і комітів

```
<ticket>-<короткий-опис>-<номер issue>      a4-optimize-plan-13
```

Коміти — conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`,
`refactor:`. Це не косметика: за історією комітів на захисті видно, хто що
робив, а завдання вимагає індивідуального захисту.

## Що робити з конфліктами

```bash
git switch main && git pull --ff-only
git switch -                     # назад у свою гілку
git rebase main                  # rebase, не merge — історія лишається лінійною
# розв'язати конфлікти, потім:
git rebase --continue
git push --force-with-lease      # --force-with-lease, ніколи не --force
```

Конфліктів майже не буде, якщо тримати межі треків: трек A чіпає тільки
`mcp_servers/`, трек B — тільки `agent/`, трек C — тільки `docs/` і `README.md`.
Спільні файли (`schemas.py`, `requirements.txt`) міняє тільки той, чий тікет це
прямо вимагає.

## Червоні лінії

- у `main` не пушимо напряму — тільки через PR;
- `--force` без `--with-lease` заборонено;
- не комітимо `.env`, реальний календар, реальний Obsidian vault, ключі;
- не міняємо схему інструмента без оновлення `docs/03-tool-contracts.md` у тому
  ж PR;
- не мерджимо PR із червоним CI.

## Якщо працюєш через Claude Code

`CLAUDE.md` у корені описує той самий цикл у форматі, який читає агент. Кожен
працює у власній сесії Claude Code; синхронізація відбувається виключно через
issues і PR, не через чат.
