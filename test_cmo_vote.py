#!/usr/bin/env python3
"""Test CMO board vote"""
import sys
sys.path.insert(0, '.')

from crewai import Task
from src.agents.cmo import get_cmo

cmo = get_cmo()

task = Task(
    description='''You are the CMO on the BBS board. Vote on this idea in ONE sentence.

Business idea: Launch an AI-powered patient education platform in Hungary, targeting GP clinics with Hungarian-language medical content subscriptions.

Respond with: VOTE: [APPROVE/REJECT] — REASON: [1 sentence]''',
    agent=cmo,
    expected_output="A single vote with reason.",
)

print("Running CMO board vote...")
result = cmo.execute_task(task)
print("=== RESULT ===")
print(result)
