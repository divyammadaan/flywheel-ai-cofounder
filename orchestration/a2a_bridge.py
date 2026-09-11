"""Cross-framework agent communication: lets ADK agents (Strategy, Finance,
Analytics) and CrewAI agents (Marketing, Product, Sales, CRM) hand off tasks
and results to each other via the A2A protocol, instead of custom glue code.

TODO: implement once google-adk and crewai agents are both live. For now,
orchestration/cycle.py calls each agent directly in-process.
"""
