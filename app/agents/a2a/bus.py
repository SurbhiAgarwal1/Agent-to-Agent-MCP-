"""In-process Message Bus for Agent-to-Agent (A2A) Communication."""

import logging
from typing import Callable, Dict, List, Optional
from app.agents.a2a.message import A2AMessage, A2AMessageType

logger = logging.getLogger("app.agents.a2a.bus")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


class MessageBus:
    """In-process message bus for routing structured A2A messages between agents."""

    def __init__(self):
        """Initialize message bus with agent registry and audit log."""
        self._handlers: Dict[str, Callable[[A2AMessage], A2AMessage]] = {}
        self._message_log: List[A2AMessage] = []

    def register_agent(self, agent_name: str, handler: Callable[[A2AMessage], A2AMessage]) -> None:
        """Register an agent's message handler on the bus.
        
        Args:
            agent_name: Unique identifier/name of the agent (e.g., 'RequirementAgent').
            handler: Callable taking an incoming A2AMessage and returning an A2AMessage.
        """
        self._handlers[agent_name] = handler
        logger.info(f"[A2A Bus] Registered agent: '{agent_name}'")

    def unregister_agent(self, agent_name: str) -> None:
        """Unregister an agent from the bus."""
        self._handlers.pop(agent_name, None)

    def send(self, message: A2AMessage) -> A2AMessage:
        """Route a structured message to its intended receiver agent.
        
        Logs message transmission, validates receiver existence, executes the handler,
        and logs the response message. Returns an A2A error message if routing fails.
        """
        # Audit log the outbound message
        self._message_log.append(message)
        logger.info(
            f"[A2A SEND] [{message.correlation_id}] {message.sender_agent} -> {message.receiver_agent} "
            f"| Type: {message.message_type} | MsgID: {message.message_id}"
        )

        receiver = message.receiver_agent
        if receiver not in self._handlers:
            err_msg = f"Receiver agent '{receiver}' is not registered on the message bus."
            logger.error(f"[A2A ERROR] {err_msg}")
            error_response = message.create_error(
                sender_agent="MessageBus",
                error_message=err_msg,
                details={"unregistered_receiver": receiver},
            )
            self._message_log.append(error_response)
            return error_response

        handler = self._handlers[receiver]
        try:
            logger.info(
                f"[A2A RECV] [{message.correlation_id}] {receiver} processing message '{message.message_type}'"
            )
            response = handler(message)
            if not isinstance(response, A2AMessage):
                err_msg = f"Handler for '{receiver}' did not return an A2AMessage instance."
                logger.error(f"[A2A ERROR] {err_msg}")
                error_response = message.create_error(
                    sender_agent=receiver,
                    error_message=err_msg,
                )
                self._message_log.append(error_response)
                return error_response

            self._message_log.append(response)
            logger.info(
                f"[A2A RESP] [{response.correlation_id}] {response.sender_agent} -> {response.receiver_agent} "
                f"| Type: {response.message_type} | MsgID: {response.message_id}"
            )
            return response

        except Exception as exc:
            logger.exception(f"[A2A EXCEPTION] Handler for '{receiver}' failed: {exc}")
            error_response = message.create_error(
                sender_agent=receiver,
                error_message=f"Agent execution failed: {str(exc)}",
                details={"exception_type": type(exc).__name__},
            )
            self._message_log.append(error_response)
            return error_response

    def get_messages_for_correlation_id(self, correlation_id: str) -> List[A2AMessage]:
        """Retrieve all recorded messages associated with a correlation ID."""
        return [msg for msg in self._message_log if msg.correlation_id == correlation_id]

    def clear_log(self) -> None:
        """Clear message history log."""
        self._message_log.clear()
