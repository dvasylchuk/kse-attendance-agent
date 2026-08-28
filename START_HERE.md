# Що робиш ти — один акаунт, кілька машин

Модель: **один GitHub-акаунт `dvasylchuk`, кілька ноутбуків, на кожному своя
сесія Claude Code.** Колаборантів не запрошуємо. Кожна машина авторизує той
самий акаунт і має власне імʼя сесії, щоб тікети не перетиналися.

## Машина 1 — створити репозиторій (робиться один раз)

```powershell
tar -xzf kse-attendance-agent.tar.gz
cd kse-attendance-agent

winget install Git.Git GitHub.cli Python.Python.3.11 OpenJS.NodeJS jq.jq
gh auth login              # GitHub.com -> HTTPS -> Login with a web browser
gh auth refresh -s project

[Environment]::SetEnvironmentVariable("AGENT_NAME", "laptop-a", "User")
# закрити й відкрити PowerShell

bash scripts/bootstrap_github.sh
```

Скрипт створює репозиторій, пушить код, робить 9 міток, 4 мілстоуни, 26 issues
із залежностями, дошку проєкту, вмикає auto-merge і захист `main`.

Обовʼязкового рев'ю навмисно немає: GitHub не дає апрувити власний PR, тому з
одним акаунтом воно б заблокувало кожен PR. Гейт — зелений CI.

## Машина 2 (і далі) — підключити до того самого репо

```powershell
winget install Git.Git GitHub.cli Python.Python.3.11 OpenJS.NodeJS jq.jq
gh auth login              # ТОЙ САМИЙ акаунт dvasylchuk
gh auth status             # переконатись, що логін правильний

[Environment]::SetEnvironmentVariable("AGENT_NAME", "laptop-b", "User")
# закрити й відкрити PowerShell

git clone https://github.com/dvasylchuk/kse-attendance-agent.git
cd kse-attendance-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # заповнити OPENROUTER_API_KEY
python scripts/verify_mcp.py
```

Все. Ніяких запрошень, ніяких прав — акаунт той самий, доступ уже є.

## Як машини не заважають одна одній

Три речі одночасно:

1. **Треки не перетинаються по каталогах.** Машина, що веде трек A, чіпає лише
   `mcp_servers/`; трек B — лише `agent/`; трек C — лише `docs/`.
2. **Клейм тікета.** `gh issue comment 12 --body "/take $env:AGENT_NAME"`. Якщо
   тікет уже взяла інша сесія, бот відмовить і назве її імʼя. Чекай на відповідь
   бота перед тим, як починати.
3. **Гілки з префіксом сесії:** `laptop-b/a3-detect-schedule-conflicts-12`.

## Що відбувається саме по собі

| Подія | Хто робить |
|---|---|
| `/take laptop-b` у issue | бот призначає, ставить `status:in-progress`, друкує назву гілки |
| відкрито PR | CI ганяє `ruff`, `pytest`, верифікацію MCP-сервера і скан на секрети |
| CI зелений | auto-merge мерджить сам, гілка видаляється |
| issue закрилась | бот знімає `status:blocked` із залежних і пише в них коментар |
| той коментар | сигнал наступній сесії, що можна починати |

Раз на день:

```powershell
gh issue list --state open --label status:ready         # що вільне
gh issue list --state open --label status:in-progress   # що зайняте і ким
gh pr list --state open                                 # що зависло
```

## Порядок роботи по машинах

Критичний шлях: `A3 → A4 → A5 → B3 → B4 → D1 → D2`.

Найшвидша розкладка на дві машини:

- **laptop-a → трек A** (`A3`, `A4`, `A5`, потім `A6`, `A7`) — це критичний шлях,
  тримай його на машині, за якою сидиш найбільше;
- **laptop-b → трек B** (`B1`, `B2`, `B5` — вони не залежать від треку A), потім
  `B3`, `B4`, `B6`, `B7`, коли `A5` закриється;
- **трек C** підбирає будь-яка вільна машина: `C1`, `C7`, `C6` можна робити з
  першого дня, `C2` і `C4` — після `A5`.

Тікети `D1`–`D4` — наприкінці, руками, бо це репетиція захисту, і пояснювати
систему на захисті маєш ти сам.

## Куди дивитись

| Файл | Про що |
|---|---|
| `PROJECT.md` | що це за проєкт і навіщо — почни звідси |
| `docs/01-plan.md` | план роботи, критичний шлях, треки |
| `docs/TICKETS.md` | всі 26 тікетів офлайн |
| `docs/02-git-workflow.md` | цикл роботи, налаштування машини |
| `CLAUDE.md` | протокол для сесії Claude Code |
| `docs/05-demo-checklist.md` | сценарій захисту по хвилинах |
| `docs/07-rubric-selfcheck.md` | що потрібно для 100 балів |
