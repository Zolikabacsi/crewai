"""Office task definitions."""

from crewai import Task
from ..agents.office_assistant import OfficeAssistant


def sync_drive_task(context: list = None) -> Task:
    """Daily Drive sync task — check for new files and ingest into vault.

    Args:
        context: Optional list of previous task outputs for context.

    Returns:
        Configured Task instance.
    """
    return Task(
        description=(
            "Check for new files in the Drive folder 'Aestas Group/Aestras Healthcare Ltd'. "
            "Use the DriveSyncTool with action='sync' to identify new files since last run. "
            "For each new file:\n"
            "1. Download it to ~/srv/vault/Aestas Vault/raw/\n"
            "2. Create wiki/sources/[name].md summary in Aestas Vault\n"
            "3. Update meta/index.md catalog\n"
            "4. Append to meta/log.md\n\n"
            "Use VaultReadTool to read new files before creating summaries."
        ),
        agent=OfficeAssistant(),
        expected_output=(
            "A report of new files synced, including downloaded file paths "
            "and a list of vault wiki entries created or updated."
        ),
        context=context,
    )
