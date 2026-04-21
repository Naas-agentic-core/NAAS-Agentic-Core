import re

with open("microservices/orchestrator_service/src/services/overmind/graph/main.py", "r") as f:
    content = f.read()

# Replace IntentClassifier
old_classifier = """class IntentClassifier(dspy.Signature):
    \"\"\"Classify if conversation needs admin system metrics, general chat/greetings, or educational search. If the user says a greeting (السلام عليكم, hello) or general chat, output is_chat=True. Follow-up questions about previous exercises/topics are educational searches, so is_chat=False.\"\"\"

    history: str = dspy.InputField(
        desc="Previous conversation context to resolve pronouns and context"
    )
    question: str = dspy.InputField()
    is_admin: bool = dspy.OutputField(desc="True if conversation needs real system counts/metrics")
    is_chat: bool = dspy.OutputField(
        desc="True if conversation is a greeting, small talk, or general conversational chat (e.g. السلام عليكم, شكرا, مرحبا)"
    )
    confidence: float = dspy.OutputField()
    tool_needed: str = dspy.OutputField(desc="Which admin tool is needed")"""

new_classifier = """class IntentClassifier(dspy.Signature):
    \"\"\"Classify if conversation needs admin system metrics, general chat/greetings, general knowledge, or educational search.
    Follow-up questions about previous exercises/topics are educational searches.
    General knowledge questions (e.g., population, capitals, history, unrelated to current subject) are general_knowledge.
    \"\"\"

    history: str = dspy.InputField(
        desc="Previous conversation context to resolve pronouns and context"
    )
    question: str = dspy.InputField()
    intent: str = dspy.OutputField(desc="One of: educational, general_knowledge, admin, chat")
    confidence: float = dspy.OutputField()
    resolved_question: str = dspy.OutputField(desc="The question rewritten with pronouns resolved using history")"""

content = content.replace(old_classifier, new_classifier)

# Replace SupervisorNode.__call__
old_supervisor = """    async def __call__(self, state: AgentState) -> dict:
        \"\"\"يوجّه النية بشكل غير حاجب للحلقة الحدثية مع أولوية للحراس الحتمية.\"\"\"
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        query = state.get("query", "")
        messages = state.get("messages", [])
        formatted_history = format_conversation_history(messages[:-1])

        if emergency_intent_guard(query):
            intent = "admin"
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return {"intent": intent}

        query_normalized = query.strip().lower()
        if any(trigger in query_normalized for trigger in CHAT_INTENT_TRIGGERS):
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return {"intent": "chat"}

        for pattern in ADMIN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "admin"}

        try:
            result = await asyncio.to_thread(
                self.dspy_classifier, history=formatted_history, question=query
            )
            try:
                conf = float(result.confidence)
            except (ValueError, TypeError):
                conf = 0.0

            if (
                hasattr(result, "is_admin")
                and str(result.is_admin).lower() == "true"
                and conf > 0.75
            ):
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "admin"}
            if hasattr(result, "is_chat") and str(result.is_chat).lower() == "true" and conf > 0.70:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "chat"}
        except Exception:
            pass

        if (
            len(query_normalized.split()) <= 3
            and "?" not in query_normalized
            and "؟" not in query
            and not _looks_elliptical_followup(query, formatted_history)
        ):
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return {"intent": "chat"}

        intent = "search"
        emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
        return {"intent": intent}"""

new_supervisor = """    async def __call__(self, state: AgentState) -> dict:
        \"\"\"يوجّه النية بشكل غير حاجب للحلقة الحدثية مع أولوية للحراس الحتمية.\"\"\"
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        query = state.get("query", "")
        messages = state.get("messages", [])
        formatted_history = format_conversation_history(messages[:-1])

        if emergency_intent_guard(query):
            intent = "admin"
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return {"intent": intent, "query": query}

        query_normalized = query.strip().lower()
        if any(trigger in query_normalized for trigger in CHAT_INTENT_TRIGGERS):
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return {"intent": "chat", "query": query}

        for pattern in ADMIN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "admin", "query": query}

        resolved_q = query
        try:
            result = await asyncio.to_thread(
                self.dspy_classifier, history=formatted_history, question=query
            )
            try:
                conf = float(result.confidence)
            except (ValueError, TypeError):
                conf = 0.0

            if hasattr(result, "resolved_question") and result.resolved_question:
                resolved_q = result.resolved_question

            pred_intent = getattr(result, "intent", "").lower().strip()

            if pred_intent == "admin" and conf > 0.75:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "admin", "query": resolved_q}
            elif pred_intent == "general_knowledge" and conf > 0.60:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "general_knowledge", "query": resolved_q}
            elif pred_intent == "chat" and conf > 0.65:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "chat", "query": resolved_q}
            elif pred_intent == "educational" and conf > 0.55:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "educational", "query": resolved_q}

        except Exception:
            pass

        if (
            len(query_normalized.split()) <= 3
            and "?" not in query_normalized
            and "؟" not in query
            and not _looks_elliptical_followup(query, formatted_history)
        ):
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return {"intent": "chat", "query": query}

        intent = "search"
        emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
        return {"intent": intent, "query": query}"""

content = content.replace(old_supervisor, new_supervisor)

with open("microservices/orchestrator_service/src/services/overmind/graph/main.py", "w") as f:
    f.write(content)
