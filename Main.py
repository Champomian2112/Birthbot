import discord
from discord.ext import tasks
import json
from datetime import datetime, time, timezone, timedelta
import asyncio
import os
from keep_alive import keep_alive

JST = timezone(timedelta(hours=9))
NOTIFY_TIME = time(hour=9, minute=0, tzinfo=JST)

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

DATA_FILE = "birthdays.json"
CONFIG_FILE = "config.json"  # ★チャンネル設定を保存するファイル

# --- データ管理用の関数 ---
def load_data(file_name):
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_data(file_name, data):
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@client.event
async def on_ready():
    print(f"ログインしました: {client.user}")
    if not check_birthday.is_running():
        check_birthday.start()

@client.event
async def on_guild_join(guild):
    """ボットがサーバーに参加したときに自動で実行されるイベント"""
    
    # ボットがメッセージを送信できる最初のテキストチャンネルを探す
    target_channel = None
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            target_channel = channel
            break

    # 送信できるチャンネルが見つからなければ終了
    if target_channel is None:
        return

    # 挨拶とコマンド一覧をリッチな見た目（埋め込みメッセージ）で作成
    embed = discord.Embed(
        title="🎂 誕生日通知ボットの導入ありがとうございます！",
        description="このサーバーのみんなの誕生日をお祝いするボットです。まずは通知用のチャンネルを設定してください！",
        color=discord.Color.from_rgb(255, 182, 193) # ピンク色
    )
    
    embed.add_field(
        name="🛠️ 最初にやること（管理者のみ）", 
        value="`!setchannel`\n通知を飛ばしたいテキストチャンネルでこのコマンドを打つと、設定が完了します。", 
        inline=False
    )
    
    embed.add_field(
        name="📝 メンバー用コマンド", 
        value="`!birthday MM-DD`\n自分の誕生日を登録します。（例： `!birthday 01-23`）", 
        inline=False
    )
    
    embed.add_field(
        name="💡 豆知識", 
        value="登録した誕生日は、設定されたチャンネルで毎朝9:00に自動でお祝いされます🎉", 
        inline=False
    )
    # チャンネルに送信
    await target_channel.send(embed=embed)
@client.event
async def on_message(message):
    if message.author.bot:
        return
    # 既存の on_message の中に追加してください
    if message.content == "!help" or message.content == "!menu":
        embed = discord.Embed(
            title="🎂 誕生日通知ボット コマンド一覧",
            color=discord.Color.blue()
        )
        embed.add_field(name="`!birthday MM-DD`", value="自分の誕生日を登録・変更します。(例: `!birthday 08-05`)", inline=False)
        embed.add_field(name="`!setchannel`", value="【管理者専用】このチャンネルを誕生日通知先に設定します。", inline=False)
        
        await message.channel.send(embed=embed)
        return
    # ★【新機能】通知チャンネルの設定コマンド
    # サーバーの管理者だけが実行できるように制限しています
    if message.content == "!setchannel":
        if not message.author.guild_permissions.administrator:
            await message.channel.send("このコマンドは管理権限を持つユーザーのみ実行できます。")
            return

        config = load_data(CONFIG_FILE)
        # サーバーIDをキーにして、チャンネルIDを保存
        config[str(message.guild.id)] = message.channel.id
        save_data(CONFIG_FILE, config)

        await message.channel.send(f"📢今後このチャンネル（{message.channel.mention}）に誕生日通知を送信するよ！")
        return

    # 誕生日登録コマンド
    if message.content.startswith("!birthday"):
        try:
            _, date = message.content.split()
            datetime.strptime(date, "%m-%d")

            data = load_data(DATA_FILE)
            data[str(message.author.id)] = date
            save_data(DATA_FILE, data)

            await message.channel.send(f"{message.author.mention} の誕生日を {date} で登録したよ！")
        except ValueError:
            await message.channel.send("使い方: `!birthday 01-23` のように入力してね")


# 毎日朝9時に実行されるタスク
@tasks.loop(time=NOTIFY_TIME)
async def check_birthday():
    await client.wait_until_ready()
    
    today = datetime.now(JST).strftime("%m-%d")
    birthday_data = load_data(DATA_FILE)
    config_data = load_data(CONFIG_FILE)

    # 登録されているユーザーを一人ずつチェック
    for user_id, birthday in birthday_data.items():
        if birthday == today:
            try:
                # ユーザーオブジェクトを取得して、その人が所属しているサーバーを探す
                user = await client.fetch_user(int(user_id))
                
                # ボットが参加している全サーバーから、そのユーザーがいるサーバーを探して通知
                for guild in client.guilds:
                    member = guild.get_member(user.id) or await guild.fetch_member(user.id).catch(None)
                    if member:
                        # そのサーバーの設定済みチャンネルIDを取得
                        channel_id = config_data.get(str(guild.id))
                        if not channel_id:
                            continue  # チャンネルが設定されていないサーバーはスキップ

                        channel = guild.get_channel(int(channel_id)) or await guild.fetch_channel(int(channel_id))
                        if channel:
                            await channel.send(f"🎉 今日は {user.mention} の誕生日だよ！おめでとう！ 🎉")
            except Exception as e:
                print(f"エラーが発生しました (ユーザーID: {user_id}): {e}")

# Renderのスリープ回避用のダミーサーバーを起動
keep_alive()

# 環境変数から「DISCORD_TOKEN」という名前の値を読み込む
TOKEN = os.environ.get('DISCORD_TOKEN')

# トークンが設定されていない場合のエラーチェック（親切設計）
if TOKEN is None:
    print("エラー: 環境変数 DISCORD_TOKEN が設定されていません。")
else:
    # ボットを起動
    client.run(TOKEN)