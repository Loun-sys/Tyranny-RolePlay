"""Discord only selects participants and grants access; combat stays on the site."""
import os
from urllib.parse import quote,urlencode
import discord
from discord import app_commands
from battle_store import BattleStore
from campaign_store import CampaignStore


class BattleParticipants(discord.ui.View):
    def __init__(self,db,guild,owner,map_id):
        super().__init__(timeout=600)
        self.db,self.guild,self.owner,self.map_id=db,guild,owner,map_id
        self.users=[];self.created=False;self.creating=False
        self.selector=discord.ui.UserSelect(placeholder='Выберите участников боя',min_values=1,max_values=25)
        self.selector.callback=self.select_users;self.add_item(self.selector)

    async def interaction_check(self,interaction):
        if interaction.user.id==self.owner:return True
        await interaction.response.send_message('Выбор участников принадлежит мастеру боя.',ephemeral=True);return False

    async def select_users(self,interaction):
        self.users=list(self.selector.values)
        await interaction.response.send_message('Выбрано участников: '+str(len(self.users))+'. Нажмите «Создать бой».',ephemeral=True)

    @discord.ui.button(label='Создать бой',style=discord.ButtonStyle.danger)
    async def create(self,interaction,button):
        if self.created or self.creating:await interaction.response.send_message('Бой уже создан или создаётся.',ephemeral=True);return
        if not self.users:await interaction.response.send_message('Сначала выберите участников.',ephemeral=True);return
        self.creating=True
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            ids=[]
            for member in self.users:
                character=await self.db.get_character(self.guild,member.id)
                if not character:raise ValueError(f'{member.display_name}: сначала создайте персонажа через /регистрация.')
                ids.append(character['id'])
            row=await BattleStore(self.db).create(self.guild,self.owner,self.map_id,ids)
            self.created=True;button.disabled=True
            await interaction.followup.send(f"Бой №{row['id']} «{row['name']}» создан. Участники вступают командой `/начать-бой бой:{row['id']}`. В мастерской откройте «БОИ», расставьте токены и нажмите «Начать бой».",ephemeral=True)
            self.stop()
        except ValueError as e:await interaction.followup.send(str(e),ephemeral=True)
        finally:self.creating=False


def register_commands(bot,is_master,guild_id,archive_site_url):
    async def maps(interaction,current):
        if not is_master(interaction):return []
        rows=await CampaignStore(bot.db).maps(guild_id(interaction),interaction.user.id)
        return [app_commands.Choice(name=m['name'][:100],value=m['id']) for m in rows if current.casefold() in m['name'].casefold()][:25]

    @bot.tree.command(name='старт-боя',description='Выбрать карту и участников общего боя — команда мастера')
    @app_commands.autocomplete(карта=maps)
    @app_commands.describe(карта='Сохранённая карта из вашей мастерской')
    async def start(interaction:discord.Interaction,карта:int):
        if not is_master(interaction):await interaction.response.send_message('Запуск боя доступен только мастеру.',ephemeral=True);return
        rows=await CampaignStore(bot.db).maps(guild_id(interaction),interaction.user.id)
        if not any(m['id']==карта for m in rows):await interaction.response.send_message('Выберите свою сохранённую карту из списка.',ephemeral=True);return
        await interaction.response.send_message('Выберите участников. Стартовые клетки и противников можно менять в админ-панели до запуска.',
            view=BattleParticipants(bot.db,guild_id(interaction),interaction.user.id,карта),ephemeral=True)

    async def invited(interaction,current):
        c=await bot.db.get_character(guild_id(interaction),interaction.user.id)
        if not c:return []
        rows=await BattleStore(bot.db).list(guild_id(interaction),cid=c['id'])
        return [app_commands.Choice(name=f"№{r['id']} · {r['name']}"[:100],value=r['id']) for r in rows if r['status']!='ended' and current.casefold() in r['name'].casefold()][:25]

    @bot.tree.command(name='начать-бой',description='Вступить в бой мастера и открыть его на сайте')
    @app_commands.autocomplete(бой=invited)
    async def join(interaction:discord.Interaction,бой:int|None=None):
        c=await bot.db.get_character(guild_id(interaction),interaction.user.id)
        if not c:await interaction.response.send_message('Сначала создайте персонажа через /регистрация.',ephemeral=True);return
        site,api=archive_site_url(),os.getenv('TYRANNY_PUBLIC_API_URL','').strip().rstrip('/')
        if not site or not api:await interaction.response.send_message('Адрес сайта ещё не настроен.',ephemeral=True);return
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            store=BattleStore(bot.db)
            rows=[r for r in await store.list(guild_id(interaction),cid=c['id']) if r['status']!='ended']
            if бой is None:
                if len(rows)!=1:raise ValueError('Выберите приглашённый бой в параметре «бой».' if rows else 'Мастер пока не пригласил вас в бой.')
                бой=rows[0]['id']
            row=await store.join(бой,guild_id(interaction),c['id'])
            token=await bot.db.create_portal_token(guild_id(interaction),interaction.user.id)
            link=f"{site}{'&' if '?' in site else '?'}{urlencode({'api':api,'battle':бой})}#token={quote(token)}"
            view=discord.ui.View();view.add_item(discord.ui.Button(label='Открыть бой',url=link))
            await interaction.followup.send(f"Вы вступили в бой «{row['name']}». Расстановка и начало — за мастером.",view=view,ephemeral=True)
        except ValueError as e:await interaction.followup.send(str(e),ephemeral=True)
