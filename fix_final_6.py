def modify_routes():
    with open('microservices/orchestrator_service/src/api/routes.py', 'r', encoding='utf-8') as f:
        content = f.read()

    search_block_routes = """    async def _stream_generator():
        try:
            prepared_objective = _augment_ambiguous_objective(
                request.question, request.history_messages
            )
            run_result = agent.run(prepared_objective, context=context)"""

    replace_block_routes = """    async def _stream_generator():
        try:
            prepared_objective = _augment_ambiguous_objective(
                request.question, request.history_messages
            )

            # Use _build_graph_messages to properly seed history for the agent context
            conversation_id_fallback = request.conversation_id if getattr(request, "conversation_id", None) else str(uuid.uuid4())
            thread_id = _resolve_thread_id(
                {"user_id": request.user_id, "conversation_id": request.conversation_id},
                fallback_conversation_id=str(conversation_id_fallback),
            )
            checkpointer_available, checkpoint_has_state = await _detect_checkpoint_state(thread_id)
            langchain_msgs = _build_graph_messages(
                objective=prepared_objective,
                history_messages=request.history_messages,
                checkpointer_available=checkpointer_available,
                checkpoint_has_state=checkpoint_has_state,
            )

            run_result = agent.run(prepared_objective, context=context, history=langchain_msgs)"""

    if search_block_routes in content:
        content = content.replace(search_block_routes, replace_block_routes)
        with open('microservices/orchestrator_service/src/api/routes.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Success routes part 1")
    else:
        print("Block not found routes part 1")

modify_routes()
