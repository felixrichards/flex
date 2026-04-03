import discord


class ParseFeedbackView(discord.ui.View):
    def __init__(self, requester_id: int):
        super().__init__(timeout=120)
        self.requester_id = requester_id
        self._resolved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                "Only the user who ran the parse can submit feedback on this result.",
                ephemeral=True,
            )
            return False
        return True

    async def _finalize(self, interaction: discord.Interaction, is_correct: bool) -> None:
        if self._resolved:
            await interaction.response.send_message("Feedback was already submitted.", ephemeral=True)
            return

        self._resolved = True
        for child in self.children:
            child.disabled = True

        status = "✅ Parse confirmed by requester." if is_correct else "❌ Parse marked incorrect by requester."
        content = (interaction.message.content or "").rstrip()
        content = f"{content}\n\n{status}" if content else status
        await interaction.response.edit_message(content=content, view=self)

    @discord.ui.button(label="Correct", style=discord.ButtonStyle.success, emoji="✅")
    async def correct(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._finalize(interaction, is_correct=True)

    @discord.ui.button(label="Wrong", style=discord.ButtonStyle.danger, emoji="❌")
    async def wrong(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._finalize(interaction, is_correct=False)

    async def on_timeout(self) -> None:
        if self._resolved:
            return
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass
