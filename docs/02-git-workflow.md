# Як працюємо з git — один акаунт, кілька машин

Модель роботи: **один GitHub-акаунт (`dvasylchuk`), кілька ноутбуків, на
кожному своя сесія Claude Code.** Колаборантів немає — усі коміти, гілки й PR
належать одному акаунту. Тому єдине місце, де сесії домовляються між собою, —
це GitHub Issues, а не чат.

Це також правильно з погляду завдання: захист індивідуальний, і історія
комітів має показувати одну людину.

## Одноразове налаштування кожної машини

```powershell
# 1. інструменти
winget install Git.Git GitHub.cli Python.Python.3.11 OpenJS.NodeJS jq.jq

# 2. авторизація того самого GitHub-акаунта
gh auth login          # GitHub.com -> HTTPS -> Login with a web browser
gh auth refresh -s project
gh auth status         # має показати dvasylchuk

# 3. імʼя цієї сесії — воно потрапляє у claim-коментарі й назви гілок
[Environment]::SetEnvironmentVariable("AGENT_NAME", "laptop-b", "User")
# закрити й відкрити PowerShell, перевірити:
echo $env:AGENT_NAME

# 4. репозиторій і оточення
git clone https://github.com/dvasylchuk/kse-attendance-agent.git
cd kse-attendance-agent
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # заповнити OPENROUTER_API_KEY
python scripts/verify_mcp.py    # має вивести 5 інструментів
```

`.env` у `.gitignore`. Ключі в репозиторій не потрапляють — це окремий пункт
рубрики, за який знімають бали.

## Щоденний цикл

```bash
# 1. синхронізуватись і подивитись, що робить інша машина
git switch main && git pull --ff-only
gh pr list --state open
bash scripts/next_ticket.sh track:A-server

# 2. взяти тікет, обовʼязково з іменем сесії
gh issue comment 12 --body "/take $AGENT_NAME"
#    прочитати відповідь бота: або підтвердження, або відмова

# 3. гілка з префіксом сесії
git switch -c "$AGENT_NAME/a3-detect-schedule-conflicts-12"

# 4. робота, дрібні коміти
git add -A && git commit -m "feat(mcp): detect calendar conflicts"

# 5. перевірка перед пушем
ruff check . && pytest -q && python scripts/verify_mcp.py

# 6. PR і авто-мерж
git push -u origin HEAD
gh pr create --fill --body "Closes #12

Session: $AGENT_NAME"
gh pr merge --squash --delete-branch --auto
```

Рев'ю не потрібне: GitHub не дозволяє апрувити власний PR, тому з одним
акаунтом обовʼязкове рев'ю просто заблокувало б усе. Замість нього гейт — зелений
CI. `--auto` змерджить одразу, щойно тести пройдуть.

**Виняток: `--auto` не можна ставити на PR, який чіпає `.github/`,
`schemas.py` або будь-що в `scripts/`.** Такий PR мерджиться руками, тільки
після того, як людина прочитала повний diff. Причина: людського рев'ю на
проєкті нема взагалі, а це три місця, де помилка коштує найдорожче —
права CI/workflow, заморожений контракт інструментів, і скрипти, яким довіряє
кожна машина.

Після мержу issue закривається (через `Closes #12`), а воркфлоу
`unblock-dependents` знімає `status:blocked` із залежних тікетів і пише в них
коментар. **Цей коментар — сигнал наступній сесії**, на цій же машині чи на
іншій.

## Статуси тікета

| Мітка | Що означає | Хто ставить |
|---|---|---|
| `status:ready` | вільний, залежності закриті | бот |
| `status:in-progress` | якась сесія взяла через `/take` | бот |
| `status:blocked` | чекає на інший тікет | бот |
| закрито | PR змерджено | автоматично |

Хто саме тримає тікет, видно в коментарі бота: `Claimed by session laptop-b`.
Відпустити тікет, якщо машина до нього не повернеться:
`gh issue comment 12 --body "/drop"`.

## Чому сесії не конфліктують

Треки не перетинаються по каталогах:

| Трек | Каталог |
|---|---|
| A | `mcp_servers/` |
| B | `agent/` |
| C | `docs/`, `README.md` |

Одна машина веде один трек за раз. Спільні файли (`schemas.py`,
`requirements.txt`, `pyproject.toml`) міняє тільки та сесія, чий тікет це прямо
вимагає, і згадує це в PR.

Друге страхування — `/take`: якщо тікет уже `status:in-progress`, бот відмовляє
й називає сесію, яка його тримає. Тому перед роботою завжди чекай на відповідь
бота, а не починай одразу після коментаря.

## Що робити з конфліктами

```bash
git switch main && git pull --ff-only
git switch -                     # назад у свою гілку
git rebase main                  # rebase, не merge — історія лишається лінійною
# розв'язати конфлікти, потім:
git rebase --continue
git push --force-with-lease      # --force-with-lease, ніколи не --force
```

## Червоні лінії

- у `main` не пушимо напряму, навіть з машини власника;
- `--force` без `--with-lease` заборонено;
- не працюємо над тікетом, який не вдалося заклеймити;
- не комітимо `.env`, токени, реальний календар, реальний Obsidian vault;
- не міняємо схему інструмента без оновлення `docs/03-tool-contracts.md` у тому
  ж PR;
- не мерджимо PR із червоним CI.

## Якщо машина працює через Claude Code

`CLAUDE.md` у корені — це той самий цикл у форматі, який читає агент: як
визначити імʼя сесії, як заклеймити тікет, як не залізти в чужий трек, як
підхопити роботу, яку залишила інша машина. Кожна сесія читає його на старті.
