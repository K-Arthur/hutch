# Starter bot templates

Templates are starting configurations, not finished integrations or guarantees that a bot can complete every task. They create a bot with its own instructions, tools, policy rules, model preset, and optional schedule. `hutch bot templates` and the web app show the same catalogue.

Templates contain task instructions, tool permissions, policy rules and an optional schedule; they do not fabricate a model, run, transcript or result. Choose a configured local or hosted model route when creating the bot. Hutch refuses to start until a real route is selected and available.

Templates marked **needs a folder** expect files or a repository that you choose. Give the bot a working folder when you create it, or set one afterward. Without one, its private workspace starts empty. Review the template's input, outputs, schedule, tools, and policy before connecting it to real data.

Sales and support templates draft material for a person to review and send. They have no sending tool. Engineering report templates include command rules, but command rules are policy checks; the operating-system sandbox is the boundary for shell execution when available and enabled. A template's instructions do not grant authority, and a model can still make mistakes. Keep copies of important files and inspect proposed changes before allowing them.

Scheduled templates use UTC unless their configuration is changed. Schedules do not guarantee that a sleeping computer will run work while it is off. Provider access, network access, costs, and data movement depend on the selected model and enabled tools; see [model and provider configuration](models.md), [connections](connections.md), and [safety](safety.md).
