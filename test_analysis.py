# The user claims I didn't fix `_stream_chat_langgraph` which handles the websocket.
# Wait, `_stream_chat_langgraph` DOES use `_build_graph_messages`. It has:
# langchain_msgs = _build_graph_messages(...)
# So the context-building fix IS being used there!
# What exactly did the code review mean by: "The user explicitly asked to verify if _stream_chat_langgraph also misses _build_graph_messages. The agent ignored applying the actual context-building fix to the streaming endpoint (which handles the live websocket chat, where the issue was most likely observed)."
# Oh... is the memory rule I tried to implement the ONLY fix needed?
# "To prevent 'Context Blindness' in the LangGraph Orchestrator microservice ... always extract client_context_messages from the incoming WebSocket payload and merge it with the database history before invoking the graph."
# Let's check `_stream_chat_langgraph` in `routes.py`. It is called by `chat_ws_stategraph`.
