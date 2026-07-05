"""Dépôt du corpus vers docflow — étape `depositing → deposited` du pipeline.

Posture **client MCP** de la stack (fondations §3) : c'est le seul module
qui franchit la frontière vers docflow. Le reste du backend ne connaît que
l'interface `CorpusDepositor`.
"""
