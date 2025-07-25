import os
import matplotlib.pyplot as plt
import discord

def generate_stats_embed(username, stats):
    embed = discord.Embed(title=f"📊 Stats pour {username}", color=discord.Color.blue())
    for k, v in stats.items():
        embed.add_field(name=k.replace('_', ' ').title(), value=str(v), inline=True)
    return embed

def generate_genre_chart(genre_data: dict, filename: str = "genre_chart.png") -> str:
    if not genre_data:
        raise ValueError("Aucune donnée de genre fournie.")

    labels = list(genre_data.keys())
    sizes = list(genre_data.values())

    plt.figure(figsize=(6, 6))
    plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
    plt.axis('equal')
    plt.title("Répartition des genres")

    output_path = os.path.join("temp", filename)
    os.makedirs("temp", exist_ok=True)
    plt.savefig(output_path)
    plt.close()

    return output_path
