"""In-process Message Bus for Agent-to-Agent (A2A) Communication."""

import logging
from typing import Callable, Dict, List, Optional
from app.agents.a2a.message import A2AMessage, A2AMessageType

logger = logging.getLogger("app.agents.a2a.bus")


class MessageBus:
    """In-process message bus for routing structured A2A messages between agents."""

    def __init__(self, hub: Optional[str] = None):
        """Initialize message bus with agent registry and audit log.

        Args:
            hub: Optional name of the coordinating agent. When set, every message must
                have the hub as its sender or receiver, so agents cannot talk to each
                other directly and all traffic is visible to (and routed by) the hub.
        """
        self.hub = hub
        self._handlers: Dict[str, Callable[[A2AMessage], A2AMessage]] = {}
        self._message_log: List[A2AMessage] = []

    def register_agent(self, agent_name: str, handler: Callable[[A2AMessage], A2AMessage]) -> None:
        """Register an agent's message handler on the bus.
        
        Args:
            agent_name: Unique identifier/name of the agent (e.g., 'RequirementAgent').
            handler: Callable taking an incoming A2AMessage and returning an A2AMessage.
        """
        self._handlers[agent_name] = handler
        logger.info("A2A compatibility handler registered")

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
        logger.info("A2A compatibility message routed")

        receiver = message.receiver_agent
        if self.hub and self.hub not in (message.sender_agent, receiver):
            err_msg = (
                f"Direct agent-to-agent message {message.sender_agent} -> {receiver} refused: "
                f"all traffic must go through '{self.hub}'."
            )
            logger.warning("A2A compatibility route rejected")
            error_response = message.create_error(
                sender_agent="MessageBus",
                error_message=err_msg,
                details={"hub": self.hub},
            )
            self._message_log.append(error_response)
            return error_response

        if receiver not in self._handlers:
            err_msg = f"Receiver agent '{receiver}' is not registered on the message bus."
            logger.warning("A2A compatibility recipient unavailable")
            error_response = message.create_error(
                sender_agent="MessageBus",
                error_message=err_msg,
                details={"unregistered_receiver": receiver},
            )
            self._message_log.append(error_response)
            return error_response

        handler = self._handlers[receiver]
        try:
            logger.info("A2A compatibility handler executing")
            response = handler(message)
            if not isinstance(response, A2AMessage):
                err_msg = f"Handler for '{receiver}' did not return an A2AMessage instance."
                logger.warning("A2A compatibility handler returned an invalid response")
                error_response = message.create_error(
                    sender_agent=receiver,
                    error_message=err_msg,
                )
                self._message_log.append(error_response)
                return error_response

            self._message_log.append(response)
            logger.info("A2A compatibility handler completed")
            return response

        except Exception as exc:
            logger.error("A2A compatibility handler failed (%s)", type(exc).__name__)
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
