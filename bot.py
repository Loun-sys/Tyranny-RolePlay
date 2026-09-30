"""Discord-бот для русской текстовой адаптации Tyranny."""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path
from urllib.parse import quote, urlencode

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from card_renderer import render_character_card
from combat import LobbyView, create_combat
from constants import (
    ACCENT_SIGILS, ATTRIBUTES, BACKGROUNDS, CORE_SIGILS, ENHANCEMENT_SIGILS,
    EQUIPMENT_SLOTS, EXPRESSION_SIGILS, ITEM_CATEGORIES, REPUTATION_FACTIONS, SKILLS,
    SPECIALIZATIONS, SPIRE_UPGRADES, TALENT_TREES,
)
from database import Database
from mechanics_data import MECHANICS
from registration_api import start_registration_api
from talent_data import TALENT_BY_NAME, TALENTS, TALENTS_BY_TREE
from wiki_importer import sync_wiki

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("tyranny")

DATA_DIR = Path(os.getenv("TYRANNY_DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEST_GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0") or 0)
MASTER_ROLE_IDS = {
    int(value.strip()) for value in os.getenv("TYRANNY_MASTER_ROLE_IDS", "").split(",") if value.strip().isdigit()
}
BRONZE = discord.Color.from_rgb(139, 79, 42)
CRIMSON = discord.Color.from_rgb(111, 27, 25)


def archive_site_url() -> str:
    explicit = os.getenv("TYRANNY_ARCHIVE_URL", "").strip()
    if explicit:
        return explicit
    root = os.getenv("TYRANNY_REGISTRATION_URL", "").strip().split("?", 1)[0].rstrip("/")
    return f"{root}/archive.html" if root else ""


def guild_id(interaction: discord.Interaction) -> int:
    if interaction.guild_id is None:
        raise app_commands.NoPrivateMessage("Команда доступна только на сервере.")
    return interaction.guild_id


def is_master(interaction: discord.Interaction) -> bool:
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    return member.guild_permissions.administrator or member.guild_permissions.manage_guild or any(
        role.id in MASTER_ROLE_IDS for role in member.roles
    )


async def require_character(interaction: discord.Interaction, member: discord.Member | discord.User | None = None):
    target = member or interaction.user
    character = await bot.db.get_character(guild_id(interaction), target.id)
    if not character:
        await interaction.response.send_message(
            "Персонаж не найден. Создайте его командой `/регистрация`.", ephemeral=True
        )
        return None
    return character


def character_embed(character: dict) -> discord.Embed:
    embed = discord.Embed(title=character["name"], color=CRIMSON)
    embed.description = (
        f'**Вершитель Судеб · {character["level"]} уровень**\n'
        f'Происхождение: **{character["background"]}**\n'
        f'Специализации: **{character["specialization_1"]}** и **{character["specialization_2"]}**'
    )
    attrs = character["attributes"]
    embed.add_field(
        name="Характеристики",
        value="\n".join(f"**{name}:** {attrs[name]}" for name in ATTRIBUTES),
        inline=True,
    )
    embed.add_field(
        name="Состояние",
        value=(
            f'**Здоровье:** {character["health"]}/{character["health_max"]}\n'
            f'**Раны:** {character["wounds"]}\n'
            f'**Опыт:** {character["experience"]}'
        ),
        inline=True,
    )
    if character.get("portrait_url", "").startswith("https://"):
        embed.set_thumbnail(url=character["portrait_url"])
    embed.set_footer(text="Тирания · архив жителей Империи")
    return embed


class CharacterView(discord.ui.View):
    def __init__(self, character: dict):
        super().__init__(timeout=600)
        self.character = character

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.character["user_id"] and not is_master(interaction):
            await interaction.response.send_message("Эта панель принадлежит другому персонажу.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Карточка", emoji="📜", style=discord.ButtonStyle.primary)
    async def card(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        current = await bot.db.get_character(interaction.guild_id, self.character["user_id"])
        inventory = await bot.db.inventory(current["id"])
        image = render_character_card(current, inventory)
        await interaction.followup.send(file=discord.File(image, filename="vershitel-sudeb.png"), ephemeral=True)

    @discord.ui.button(label="Навыки", emoji="⚔️", style=discord.ButtonStyle.secondary)
    async def skills(self, interaction: discord.Interaction, _: discord.ui.Button):
        current = await bot.db.get_character(interaction.guild_id, self.character["user_id"])
        ordered = sorted(current["skills"].items(), key=lambda pair: (-pair[1]["value"], pair[0]))
        embed = discord.Embed(title=f'Навыки · {current["name"]}', color=BRONZE)
        chunks = [ordered[index:index + 8] for index in range(0, len(ordered), 8)]
        for index, chunk in enumerate(chunks, 1):
            embed.add_field(
                name=f"Раздел {index}",
                value="\n".join(f'**{name}:** {data["value"]}' for name, data in chunk),
                inline=True,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Экипировка", emoji="🛡️", style=discord.ButtonStyle.secondary)
    async def equipment(self, interaction: discord.Interaction, _: discord.ui.Button):
        rows = await bot.db.inventory(self.character["id"])
        equipped = [row for row in rows if row["equipped_slot"]]
        embed = discord.Embed(title="Экипировка", color=BRONZE)
        embed.description = "\n".join(
            f'**{row["equipped_slot"]}:** {row["name"]} ({row["quality"]})' for row in equipped
        ) or "Ничего не экипировано."
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Таланты", emoji="✨", style=discord.ButtonStyle.secondary)
    async def talents(self, interaction: discord.Interaction, _: discord.ui.Button):
        current = await bot.db.get_character(interaction.guild_id, self.character["user_id"])
        embed = discord.Embed(title="Таланты и способности", color=BRONZE)
        if current["talents"]:
            for talent in current["talents"][:25]:
                embed.add_field(
                    name=f'{talent["tree_name"]} · {talent["name"]}',
                    value=talent["description"][:1024] or "Описание отсутствует.", inline=False,
                )
        else:
            embed.description = "Таланты ещё не изучены."
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Гримуар", emoji="🔮", style=discord.ButtonStyle.secondary)
    async def spellbook(self, interaction: discord.Interaction, _: discord.ui.Button):
        spells = await bot.db.spells(self.character["id"])
        embed = discord.Embed(title="Гримуар", color=discord.Color.dark_purple())
        for spell in spells[:25]:
            additions = spell["accents"] + spell["enhancements"]
            embed.add_field(
                name=f'{spell["name"]} · сложность {spell["difficulty"]}',
                value=f'**Основа:** {spell["core"]}\n**Выражение:** {spell["expression"]}\n**Дополнения:** {", ".join(additions) or "нет"}',
                inline=False,
            )
        if not spells:
            embed.description = "Гримуар пуст. Используйте `/заклинание-создать`."
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Личное дело", emoji="🔐", style=discord.ButtonStyle.danger, row=1)
    async def portal(self, interaction: discord.Interaction, _: discord.ui.Button):
        site, api = archive_site_url(), os.getenv("TYRANNY_PUBLIC_API_URL", "").strip().rstrip("/")
        if not site or not api:
            await interaction.response.send_message("Адрес личного кабинета ещё не настроен.", ephemeral=True)
            return
        token = await bot.db.create_portal_token(interaction.guild_id, self.character["user_id"])
        if not token:
            await interaction.response.send_message("Персонаж не найден.", ephemeral=True)
            return
        separator = "&" if "?" in site else "?"
        link = f"{site}{separator}{urlencode({'api': api})}#token={quote(token)}"
        view = discord.ui.View(timeout=900)
        view.add_item(discord.ui.Button(label="Открыть личное дело", emoji="⚖️", url=link))
        await interaction.response.send_message(
            "Персональная ссылка создана на **30 дней**. Новая ссылка отзовёт предыдущую; не пересылайте её другим.",
            view=view, ephemeral=True,
        )


class TyrannyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!tyranny ", intents=intents)
        self.db = Database(DATA_DIR / "tyranny.sqlite3")

    async def setup_hook(self) -> None:
        await self.db.initialize()
        self.registration_runner = await start_registration_api(self, self.db, DATA_DIR)
        if TEST_GUILD_ID:
            guild = discord.Object(id=TEST_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Синхронизировано команд на тестовом сервере: %s", len(synced))
        else:
            synced = await self.tree.sync()
            log.info("Глобально синхронизировано команд: %s", len(synced))


bot = TyrannyBot()


@bot.event
async def on_ready():
    log.info("Tyranny-бот подключён как %s", bot.user)


@bot.tree.command(name="бой", description="Открыть полностью кнопочную боевую сцену")
async def combat_command(interaction: discord.Interaction):
    if not is_master(interaction):
        await interaction.response.send_message("Создать боевую сцену может мастер игры.", ephemeral=True)
        return
    created, result = await create_combat(interaction, bot.db)
    if not created:
        await interaction.response.send_message(str(result), ephemeral=True)
        return
    session = result
    await interaction.response.send_message(embed=session.embed(), view=LobbyView(session))
    session.message = await interaction.original_response()


@bot.tree.command(name="регистрация", description="Получить личную ссылку на конструктор Вершителя Судеб")
async def registration(interaction: discord.Interaction):
    site_url = os.getenv("TYRANNY_REGISTRATION_URL", "").strip()
    api_url = os.getenv("TYRANNY_PUBLIC_API_URL", "").strip().rstrip("/")
    if not site_url or not api_url:
        await interaction.response.send_message(
            "Конструктор ещё не опубликован: мастер должен задать `TYRANNY_REGISTRATION_URL` и `TYRANNY_PUBLIC_API_URL`.",
            ephemeral=True,
        )
        return
    token = await bot.db.create_registration_token(guild_id(interaction), interaction.user.id)
    separator = "&" if "?" in site_url else "?"
    link = f"{site_url}{separator}{urlencode({'token': token, 'api': api_url})}"
    embed = discord.Embed(title="Создание Вершителя Судеб", color=BRONZE)
    embed.description = (
        "Откройте личный конструктор, распределите характеристики и навыки, добавьте портрет и нажмите "
        "**«Сохранить в Дискорде»**.\n\nСсылка одноразовая, действует **2 часа** и привязана к вашему профилю в Дискорде."
    )
    view = discord.ui.View(timeout=7200)
    view.add_item(discord.ui.Button(label="Открыть конструктор", emoji="⚖️", url=link))
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="персонаж", description="Открыть личное дело и панель персонажа")
@app_commands.describe(участник="Чьё личное дело показать")
async def character_command(interaction: discord.Interaction, участник: discord.Member | None = None):
    character = await require_character(interaction, участник)
    if not character:
        return
    await interaction.response.send_message(embed=character_embed(character), view=CharacterView(character))


@bot.tree.command(name="архив", description="Открыть архив всех созданных персонажей")
async def archive_command(interaction: discord.Interaction):
    site, api = archive_site_url(), os.getenv("TYRANNY_PUBLIC_API_URL", "").strip().rstrip("/")
    if not site or not api:
        await interaction.response.send_message("Архив ещё не опубликован.", ephemeral=True)
        return
    separator = "&" if "?" in site else "?"
    link = f"{site}{separator}{urlencode({'api': api})}"
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="Открыть архив", emoji="📚", url=link))
    await interaction.response.send_message("Архив жителей Империи Кайрос.", view=view, ephemeral=True)


@bot.tree.command(name="портрет", description="Установить прямую HTTPS-ссылку на портрет")
async def portrait(interaction: discord.Interaction, ссылка: str):
    character = await require_character(interaction)
    if not character:
        return
    if not ссылка.startswith("https://"):
        await interaction.response.send_message("Нужна безопасная ссылка, начинающаяся с `https://`.", ephemeral=True)
        return
    await bot.db.update_character_text(character["id"], "portrait_url", ссылка[:1000])
    await interaction.response.send_message("Портрет сохранён.", ephemeral=True)


@bot.tree.command(name="характеристика", description="Изменить характеристику персонажа — мастерская команда")
@app_commands.choices(характеристика=[app_commands.Choice(name=value, value=value) for value in ATTRIBUTES])
async def attribute_command(
    interaction: discord.Interaction, участник: discord.Member,
    характеристика: app_commands.Choice[str], значение: app_commands.Range[int, 1, 30],
):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    character = await require_character(interaction, участник)
    if not character:
        return
    await bot.db.set_attribute(character["id"], характеристика.value, значение)
    await interaction.response.send_message(f'**{характеристика.value}** персонажа {участник.mention}: **{значение}**.')


@bot.tree.command(name="навык", description="Установить значение навыка — мастерская команда")
@app_commands.choices(навык=[app_commands.Choice(name=value, value=value) for value in SKILLS])
async def skill_command(
    interaction: discord.Interaction, участник: discord.Member,
    навык: app_commands.Choice[str], значение: app_commands.Range[int, 0, 300],
):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    character = await require_character(interaction, участник)
    if not character:
        return
    await bot.db.set_skill(character["id"], навык.value, значение)
    await interaction.response.send_message(f'Навык **{навык.value}** персонажа {участник.mention}: **{значение}**.')


@bot.tree.command(name="здоровье", description="Нанести урон или восстановить здоровье — мастерская команда")
@app_commands.describe(изменение="Отрицательное число наносит урон, положительное лечит")
async def health_command(interaction: discord.Interaction, участник: discord.Member, изменение: app_commands.Range[int, -999, 999]):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    character = await require_character(interaction, участник)
    if not character:
        return
    before, after = await bot.db.adjust_health(character["id"], изменение)
    await interaction.response.send_message(f'Здоровье {участник.mention}: **{before} → {after}**.')


@bot.tree.command(name="опыт", description="Выдать или снять опыт — мастерская команда")
async def experience_command(interaction: discord.Interaction, участник: discord.Member, изменение: app_commands.Range[int, -999999, 999999]):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    character = await require_character(interaction, участник)
    if not character:
        return
    experience, level, next_level = await bot.db.adjust_experience(character["id"], изменение)
    await interaction.response.send_message(f'{участник.mention}: **{experience} опыта**, **{level} уровень**; следующий порог — {next_level}.')


async def talent_autocomplete(_: discord.Interaction, current: str):
    folded = current.casefold()
    return [app_commands.Choice(name=f'{t["tree"]} · {t["name"]}', value=t["name"]) for t in TALENTS if folded in t["name"].casefold()][:25]


@bot.tree.command(name="талант-добавить", description="Изучить талант Вершителя Судеб — мастерская команда")
@app_commands.autocomplete(название=talent_autocomplete)
async def add_talent(interaction: discord.Interaction, участник: discord.Member, название: str):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    talent = TALENT_BY_NAME.get(название.casefold())
    if not talent:
        await interaction.response.send_message("Талант не найден в русской базе.", ephemeral=True)
        return
    character = await require_character(interaction, участник)
    if not character:
        return
    added = await bot.db.add_talent(character["id"], talent)
    await interaction.response.send_message("Талант изучен." if added else "Этот талант уже изучен.", ephemeral=True)


@bot.tree.command(name="таланты", description="Открыть русские деревья талантов Вершителя Судеб")
@app_commands.choices(дерево=[app_commands.Choice(name=value, value=value) for value in TALENT_TREES])
async def talents_catalog(interaction: discord.Interaction, дерево: app_commands.Choice[str]):
    embed = discord.Embed(title=f'Дерево талантов · {дерево.value}', color=BRONZE)
    for talent in TALENTS_BY_TREE[дерево.value]:
        embed.add_field(
            name=f'{talent["name"]} · требуется очков в дереве: {talent["tier"]}',
            value=talent["description"], inline=False,
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def item_autocomplete(_: discord.Interaction, current: str):
    rows = await bot.db.catalog_search(current, limit=25)
    return [app_commands.Choice(name=row["name"][:100], value=row["name"]) for row in rows]


@bot.tree.command(name="предмет-поиск", description="Найти предмет в русском каталоге Тирании")
@app_commands.autocomplete(название=item_autocomplete)
async def item_search(interaction: discord.Interaction, название: str):
    rows = await bot.db.catalog_search(название, limit=10)
    if not rows:
        await interaction.response.send_message("Предмет не найден. Мастер может обновить каталог с Wiki.", ephemeral=True)
        return
    row = rows[0]
    embed = discord.Embed(title=row["name"], description=row["description"][:4000], color=BRONZE, url=row["source_url"] or None)
    embed.add_field(name="Категория", value=row["category"])
    embed.add_field(name="Качество", value=row["quality"])
    embed.add_field(name="Стоимость", value=str(row["value"]))
    if row["image_url"]:
        embed.set_image(url=row["image_url"])
    embed.set_footer(text="Источник: русская вики Тирании")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="справочник", description="Открыть переведённый справочник механик Тирании")
@app_commands.choices(тема=[app_commands.Choice(name=name, value=name) for name in MECHANICS])
async def mechanics_guide(interaction: discord.Interaction, тема: app_commands.Choice[str]):
    article = MECHANICS[тема.value]
    embed = discord.Embed(
        title=тема.value, description=article["text"], color=BRONZE, url=article["source"]
    )
    embed.set_footer(text="Переведено с англоязычной вики Тирании · интерфейс полностью русский")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="репутация", description="Изменить Благосклонность или Гнев — мастерская команда")
@app_commands.choices(
    сторона=[app_commands.Choice(name=name, value=name) for name in REPUTATION_FACTIONS],
    шкала=[
        app_commands.Choice(name="Благосклонность", value="favor"),
        app_commands.Choice(name="Гнев", value="wrath"),
    ],
)
async def reputation_command(
    interaction: discord.Interaction, участник: discord.Member,
    сторона: app_commands.Choice[str], шкала: app_commands.Choice[str],
    изменение: app_commands.Range[int, -100, 100],
):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    character = await require_character(interaction, участник)
    if not character:
        return
    before, after = await bot.db.adjust_reputation(
        character["id"], сторона.value, шкала.value, изменение
    )
    axis_name = "Благосклонность" if шкала.value == "favor" else "Гнев"
    await interaction.response.send_message(
        f'{участник.mention} · **{сторона.value}** · {axis_name}: **{before} → {after}**.'
    )


@bot.tree.command(name="репутации", description="Показать Благосклонность и Гнев фракций")
async def reputations_command(interaction: discord.Interaction, участник: discord.Member | None = None):
    character = await require_character(interaction, участник)
    if not character:
        return
    rows = await bot.db.reputations(character["id"])
    embed = discord.Embed(title=f'Репутация · {character["name"]}', color=BRONZE)
    embed.description = "\n".join(
        f'**{row["faction"]}:** Благосклонность {row["favor"]} · Гнев {row["wrath"]}'
        for row in rows
    ) or "Значимые отношения ещё не сформированы."
    embed.set_footer(text="Шкалы независимы: Благосклонность не уменьшает Гнев")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="эдикт-создать", description="Провозгласить или изменить Эдикт Кайрос — мастерская команда")
async def create_edict(
    interaction: discord.Interaction, название: app_commands.Range[str, 2, 80],
    область: app_commands.Range[str, 2, 120], условие_снятия: app_commands.Range[str, 2, 500],
    последствия: app_commands.Range[str, 2, 1000], срок: str = "",
):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    await bot.db.save_edict(
        guild_id(interaction), название, область, условие_снятия, срок, последствия, interaction.user.id
    )
    await interaction.response.send_message(f'Эдикт **{название}** провозглашён над областью **{область}**.')


@bot.tree.command(name="эдикты", description="Показать действующие Эдикты Кайрос")
async def edicts_command(interaction: discord.Interaction):
    rows = await bot.db.edicts(guild_id(interaction))
    embed = discord.Embed(title="Действующие Эдикты Кайрос", color=CRIMSON)
    for row in rows[:25]:
        deadline = f'\n**Срок:** {row["deadline"]}' if row["deadline"] else ""
        embed.add_field(
            name=f'{row["name"]} · {row["region"]}',
            value=f'**Условие снятия:** {row["ending_condition"]}{deadline}\n**Последствия:** {row["effects"]}'[:1024],
            inline=False,
        )
    if not rows:
        embed.description = "Действующих Эдиктов нет."
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="эдикт-завершить", description="Отметить Эдикт завершённым — мастерская команда")
async def resolve_edict_command(interaction: discord.Interaction, название: str):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    success = await bot.db.resolve_edict(guild_id(interaction), название)
    await interaction.response.send_message("Эдикт завершён." if success else "Эдикт не найден.", ephemeral=True)


@bot.tree.command(name="шпиль-настроить", description="Добавить Шпиль или изменить его улучшение — мастерская команда")
@app_commands.choices(улучшение=[app_commands.Choice(name=name, value=name) for name in SPIRE_UPGRADES])
async def configure_spire(
    interaction: discord.Interaction, название: app_commands.Range[str, 2, 80],
    местоположение: app_commands.Range[str, 2, 120], улучшение: app_commands.Choice[str], заметки: str = "",
):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    await bot.db.save_spire(guild_id(interaction), название, местоположение, улучшение.value, заметки)
    await interaction.response.send_message(
        f'Шпиль **{название}** сохранён. Улучшение: **{улучшение.value}**.', ephemeral=True
    )


@bot.tree.command(name="шпили", description="Показать сеть Шпилей Вершителя Судеб")
async def spires_command(interaction: discord.Interaction):
    rows = await bot.db.spires(guild_id(interaction))
    embed = discord.Embed(title="Шпили Терратуса", color=BRONZE)
    for row in rows[:25]:
        text = f'**Местоположение:** {row["location"]}\n**Улучшение:** {row["upgrade_name"]}'
        if row["notes"]:
            text += f'\n{row["notes"]}'
        embed.add_field(name=row["name"], value=text[:1024], inline=False)
    if not rows:
        embed.description = "Ни один Шпиль ещё не заявлен."
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="предмет-выдать", description="Выдать предмет персонажу — мастерская команда")
@app_commands.autocomplete(название=item_autocomplete)
async def give_item(interaction: discord.Interaction, участник: discord.Member, название: str, количество: app_commands.Range[int, 1, 100] = 1):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    character = await require_character(interaction, участник)
    if not character:
        return
    success = await bot.db.give_item(character["id"], название, количество)
    await interaction.response.send_message(
        f'{участник.mention} получает **{название} ×{количество}**.' if success else "Предмет не найден в каталоге.",
        ephemeral=not success,
    )


@bot.tree.command(name="инвентарь", description="Показать инвентарь персонажа")
async def inventory_command(interaction: discord.Interaction, участник: discord.Member | None = None):
    character = await require_character(interaction, участник)
    if not character:
        return
    rows = await bot.db.inventory(character["id"])
    embed = discord.Embed(title=f'Инвентарь · {character["name"]}', color=BRONZE)
    for row in rows[:25]:
        status = f' · **{row["equipped_slot"]}**' if row["equipped_slot"] else ""
        embed.add_field(
            name=f'#{row["inventory_id"]} · {row["name"]} ×{row["quantity"]}',
            value=f'{row["category"]} · {row["quality"]}{status}', inline=False,
        )
    if not rows:
        embed.description = "Инвентарь пуст."
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="предмет-удалить", description="Удалить или использовать предмет из своего инвентаря")
async def remove_item_command(
    interaction: discord.Interaction, номер_предмета: int, количество: app_commands.Range[int, 1, 100] = 1,
):
    character = await require_character(interaction)
    if not character:
        return
    success = await bot.db.remove_item(character["id"], номер_предмета, количество)
    await interaction.response.send_message("Предмет удалён из инвентаря." if success else "Предмет не найден.", ephemeral=True)


@bot.tree.command(name="экипировать", description="Поместить предмет из инвентаря в слот")
@app_commands.choices(слот=[app_commands.Choice(name=value, value=value) for value in EQUIPMENT_SLOTS])
async def equip_command(interaction: discord.Interaction, номер_предмета: int, слот: app_commands.Choice[str]):
    character = await require_character(interaction)
    if not character:
        return
    success, message = await bot.db.equip(character["id"], номер_предмета, слот.value)
    await interaction.response.send_message(message, ephemeral=not success)


@bot.tree.command(name="снять", description="Снять экипированный предмет")
async def unequip_command(interaction: discord.Interaction, номер_предмета: int):
    character = await require_character(interaction)
    if not character:
        return
    success = await bot.db.unequip(character["id"], номер_предмета)
    await interaction.response.send_message("Предмет снят." if success else "Предмет не найден.", ephemeral=True)


@bot.tree.command(name="заклинание-создать", description="Собрать заклинание из сигилов")
@app_commands.choices(
    основа=[app_commands.Choice(name=value, value=value) for value in CORE_SIGILS],
    выражение=[app_commands.Choice(name=value, value=value) for value in EXPRESSION_SIGILS],
    усиление=[app_commands.Choice(name=value, value=value) for value in ENHANCEMENT_SIGILS],
)
@app_commands.describe(
    основа="Сигил основы", выражение="Сигил выражения", акценты="Названия через запятую",
    усиление="Необязательный единственный сигил усиления", сложность="Итоговая требуемая величина Знаний",
)
async def create_spell(
    interaction: discord.Interaction, название: app_commands.Range[str, 2, 80],
    основа: app_commands.Choice[str], выражение: app_commands.Choice[str],
    сложность: app_commands.Range[int, 0, 999], акценты: str = "",
    усиление: app_commands.Choice[str] | None = None, заметки: str = "",
):
    character = await require_character(interaction)
    if not character:
        return
    accents = [part.strip() for part in акценты.split(",") if part.strip()]
    unknown = [name for name in accents if name not in ACCENT_SIGILS]
    if unknown:
        await interaction.response.send_message(
            "Неизвестные акценты: " + ", ".join(unknown) + ". Допустимые: " + ", ".join(ACCENT_SIGILS),
            ephemeral=True,
        )
        return
    if len(accents) != len(set(accents)):
        await interaction.response.send_message("Один и тот же сигил акцента нельзя добавить дважды.", ephemeral=True)
        return
    enhancements = [усиление.value] if усиление else []
    await bot.db.create_spell(
        character["id"], название, основа.value, выражение.value, accents, enhancements, сложность, заметки
    )
    await interaction.response.send_message(f'Заклинание **{название}** записано в гримуар.', ephemeral=True)


@bot.tree.command(name="гримуар", description="Показать созданные заклинания")
async def spellbook_command(interaction: discord.Interaction):
    character = await require_character(interaction)
    if not character:
        return
    spells = await bot.db.spells(character["id"])
    embed = discord.Embed(title=f'Гримуар · {character["name"]}', color=discord.Color.dark_purple())
    for spell in spells[:25]:
        embed.add_field(
            name=f'{spell["name"]} · сложность {spell["difficulty"]}',
            value=f'Основа: **{spell["core"]}**\nВыражение: **{spell["expression"]}**\nАкценты: {", ".join(spell["accents"]) or "нет"}\nУсиления: {", ".join(spell["enhancements"]) or "нет"}',
            inline=False,
        )
    if not spells:
        embed.description = "Гримуар пуст."
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="проверка", description="Выполнить процентную проверку навыка Тирании")
@app_commands.choices(навык=[app_commands.Choice(name=value, value=value) for value in SKILLS])
@app_commands.describe(сложность="Модификатор порога: отрицательный усложняет, положительный облегчает")
async def skill_check(
    interaction: discord.Interaction, навык: app_commands.Choice[str],
    сложность: app_commands.Range[int, -100, 100] = 0,
):
    character = await require_character(interaction)
    if not character:
        return
    base = character["skills"][навык.value]["value"]
    threshold = max(1, min(100, base + сложность))
    roll = random.randint(1, 100)
    critical = roll <= max(1, threshold // 10)
    fumble = roll >= 96 and roll > threshold
    if critical:
        result = "КРИТИЧЕСКИЙ УСПЕХ"
        color = discord.Color.gold()
    elif roll <= threshold:
        result = "УСПЕХ"
        color = discord.Color.green()
    elif fumble:
        result = "КРИТИЧЕСКАЯ НЕУДАЧА"
        color = discord.Color.dark_red()
    else:
        result = "НЕУДАЧА"
        color = discord.Color.red()
    embed = discord.Embed(title=f'{навык.value} · {result}', color=color)
    embed.description = f'**{character["name"]}** бросает **{roll}** против порога **{threshold}**.\nНавык: {base}; модификатор: {сложность:+d}.'
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="каталог-обновить", description="Импортировать русские предметы и изображения с вики Тирании")
async def catalog_sync(interaction: discord.Interaction):
    if not is_master(interaction):
        await interaction.response.send_message("Команда доступна мастеру игры.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    count, warnings = await sync_wiki(bot.db, DATA_DIR / "tyranny_catalog.json")
    message = f"Русский каталог обновлён: **{count} страниц**."
    if warnings:
        message += "\nНе удалось прочитать категории: " + ", ".join(warnings[:5])
    await interaction.followup.send(message, ephemeral=True)


@bot.tree.command(name="удалить-персонажа", description="Безвозвратно удалить собственного персонажа")
async def delete_character_command(interaction: discord.Interaction, подтверждение: str):
    if подтверждение.casefold() != "удалить":
        await interaction.response.send_message("Для подтверждения введите слово `удалить`.", ephemeral=True)
        return
    deleted = await bot.db.delete_character(guild_id(interaction), interaction.user.id)
    await interaction.response.send_message("Персонаж удалён." if deleted else "Персонаж не найден.", ephemeral=True)


@bot.tree.error
async def command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    log.exception("Ошибка команды", exc_info=error)
    message = "Команда завершилась с ошибкой. Запись добавлена в журнал бота."
    if isinstance(error, app_commands.NoPrivateMessage):
        message = str(error)
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("В .env не задан DISCORD_TOKEN")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
