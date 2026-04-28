with open("microservices/orchestrator_service/src/api/routes.py", "r") as f:
    content = f.read()

# Replace graph creation in admin_stream
content = content.replace(
    'admin_app = getattr(fastapi_req.app.state, "admin_app", None)\n                if admin_app is None:\n                    admin_app = create_unified_graph()\n                    logger.warning("[ADMIN_STREAM] admin_app not on app.state — using fresh graph")',
    'admin_app = getattr(fastapi_req.app.state, "admin_app", None)\n                if admin_app is None:\n                    raise RuntimeError("Graph not initialized")'
)

# replace inputs for admin_stream
content = content.replace(
    '''langchain_msgs = _build_graph_messages_manual(
                    objective=prepared_objective,
                    history_messages=request.history_messages,
                )

                admin_inputs = _merge_admin_inputs(
                    {
                        "query": prepared_objective,
                        "messages": langchain_msgs,
                    },
                    admin_payload,
                )''',
    '''langchain_msgs = [{"role": "user", "content": prepared_objective}]

                admin_inputs = _merge_admin_inputs(
                    {
                        "messages": langchain_msgs,
                    },
                    admin_payload,
                )'''
)

# replace inputs for fallback generator
content = content.replace(
    '''langchain_msgs = _build_graph_messages_manual(
                objective=prepared_objective,
                history_messages=request.history_messages,
            )

            run_result = agent.run(
                prepared_objective, context=context, history_messages=langchain_msgs
            )''',
    '''langchain_msgs = [{"role": "user", "content": prepared_objective}]

            run_result = agent.run(
                prepared_objective, context=context, history_messages=langchain_msgs
            )'''
)

with open("microservices/orchestrator_service/src/api/routes.py", "w") as f:
    f.write(content)
