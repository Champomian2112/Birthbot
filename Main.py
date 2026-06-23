import discord
from discord.ext import tasks
import json
from datetime import datetime, time, timezone, timedelta
import asyncio
import os
import datetime as dt_module  # 名前衝突を避けるために追加
from keep_alive import keep_alive
import firebase_admin
from firebase_admin import credentials, db

JST = timezone(timedelta(hours=9))
NOTIFY_TIME = time(hour=9, minute=0, tzinfo=JST)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# --- Firebaseの初期化設定 ---
cred_json = json.loads(os.environ.get('FIREBASE_CREDENTIALS'))
cred = credentials.Certificate(cred_json)
firebase_admin.initialize_app(cred, {
    'databaseURL': os.environ.get('FIREBASE_DB_URL')
})

# 全てのサーバーデータを1つのノード（塊）で管理します
SERVER_DATA_NODE = "server_data"

def load_data(node_name):
    try:
        ref = db.reference(node_name)
        data = ref.get()
        return data if data else {}
    except Exception as e:
        print(f"データ読み込みエラー: {e}")
        return {}

def save_data(node_name, data):
    try:
        ref = db.reference(node_name)
        ref.set(data)
    except Exception as e:
        print(f"データ保存エラー: {e}")

@client.event
async def on_ready():
    print(f"ログインしました: {client.user}")
    if not check_birthdays.is_running():
        check_birthdays.start()

@client.event
async def on_guild_join(guild):
    """ボットがサーバーに参加したときに自動で実行されるイベント"""
    target_channel = None
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            target_channel = channel
            break

    if target_channel is None:
        return

    embed = discord.Embed(
        title="🎂 誕生日通知ボットです！今後何かしら機能追加予定です！",
        description="このサーバーのみんなの誕生日をお祝いします！まずは通知用のチャンネルを設定してください！",
        color=discord.Color.from_rgb(255, 182, 193)
    )
    
    embed.add_field(
        name="🛠️ 最初にやること（管理者のみ）", 
        value="`bb!setbdch`\n通知を飛ばしたいテキストチャンネルでこのコマンドを打つと、設定が完了します。", 
        inline=False
    )
    
    embed.add_field(
        name="📝 メンバー用コマンド", 
        value="`bb!setbday MM-DD`\n自分の誕生日を登録します。（例： `bb!setbday 01-23`）", 
        inline=False
    )
    
    embed.add_field(
        name="💡 このBotについて", 
        value="登録した誕生日は、設定されたチャンネルで毎朝9:00に自動でお祝いされます🎉", 
        inline=False
    )
    await target_channel.send(embed=embed)

@client.event
async def on_guild_remove(guild):
    """ボットがサーバーから退出、または追放されたときに自動で実行されるイベント"""
    data = load_data(SERVER_DATA_NODE)
    guild_id = str(guild.id)
    
    # サーバーIDの部屋があれば、そのサーバーの全データ（チャンネルID・誕生日）を丸ごと削除！
    if guild_id in data:
        del data[guild_id]
        save_data(SERVER_DATA_NODE, data)
        print(f"サーバー「{guild.name}」から退出したため、すべてのデータを完全に自動消去しました。")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content == "bb!help" or message.content == "bb!menu":
        embed = discord.Embed(
            title="🎂 誕生日通知ボット コマンド一覧",
            color=discord.Color.blue()
        )
        embed.add_field(name="`bb!setbday MM-DD`", value="自分の誕生日を登録・変更します。(例: `bb!setbday 08-05`)", inline=False)
        embed.add_field(name="`bb!setbdch`", value="【管理者専用】このチャンネルを誕生日通知先に設定します。", inline=False)
        
        await message.channel.send(embed=embed)
        return

    # 通知チャンネルの設定コマンド
    if message.content == "bb!setbdch":
        if not message.author.guild_permissions.administrator:
            await message.channel.send("このコマンドは管理権限を持つユーザーのみ実行できます。")
            return

        data = load_data(SERVER_DATA_NODE)
        guild_id = str(message.guild.id)

        # サーバーのデータ構造がなければ初期化
        if guild_id not in data:
            data[guild_id] = {"channel_id": None, "birthdays": {}}

        data[guild_id]["channel_id"] = message.channel.id
        save_data(SERVER_DATA_NODE, data)

        await message.channel.send(f"📢今後このチャンネル（{message.channel.mention}）に誕生日通知を送信するよ！")
        return

    # 誕生日登録コマンド
    if message.content.startswith("bb!setbday"):
        try:
            _, date = message.content.split()
            datetime.strptime(date, "%m-%d")

            data = load_data(SERVER_DATA_NODE)
            guild_id = str(message.guild.id)
            user_id = str(message.author.id)

            # サーバーのデータ構造がなければ初期化
            if guild_id not in data:
                data[guild_id] = {"channel_id": None, "birthdays": {}}

            # server_data -> サーバーID -> birthdays -> ユーザーID に保存
            if "birthdays" not in data[guild_id]:
                data[guild_id]["birthdays"] = {}
                
            data[guild_id]["birthdays"][user_id] = date
            save_data(SERVER_DATA_NODE, data)
            month, day = date.split("-")
            await message.channel.send(f"{message.author.mention} の誕生日を {month.lstrip('0')}月{day.lstrip('0')}日 で登録したよ！")
        except ValueError:
            await message.channel.send("使い方: `bb!setbday 01-23` のように入力してね")

# 毎日朝9時に実行されるタスク
@tasks.loop(time=NOTIFY_TIME)
async def check_birthdays():
    today = dt_module.date.today().strftime("%m-%d") 
    data = load_data(SERVER_DATA_NODE)

    # サーバーごとにデータをチェック
    for guild_id, guild_data in data.items():
        channel_id = guild_data.get("channel_id")
        if not channel_id:
            continue

        channel = client.get_channel(int(channel_id))
        if not channel:
            continue

        birthdays_list = guild_data.get("birthdays", {})
        today_celebrated = []
        for user_id, b_day in birthdays_list.items():
            if b_day == today:
                today_celebrated.append(f"<@{user_id}>")

        if today_celebrated:
            mentions = ", ".join(today_celebrated)
            await channel.send(f"🎂【本日のお誕生日】\n今日は {month}月{day}日 です！\n{mentions} さん、誕生日おめでとう！🎉")

# ダミーサーバー起動
keep_alive()

TOKEN = os.environ.get('DISCORD_TOKEN')
if TOKEN is None:
    print("エラー: 環境変数 DISCORD_TOKEN が設定されていません。")
else:
    client.run(TOKEN)
