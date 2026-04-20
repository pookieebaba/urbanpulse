"""
Socket.IO event handlers for real-time sensor streaming.
Clients join a room per zone to receive targeted updates.
"""
import logging

logger = logging.getLogger(__name__)


def register_socket_events(socketio):

    @socketio.on("connect")
    def on_connect():
        logger.info("Client connected: %s")

    @socketio.on("disconnect")
    def on_disconnect():
        logger.info("Client disconnected")

    @socketio.on("subscribe_zone")
    def on_subscribe(data):
        """Client sends { zone_id: "..." } to subscribe to a zone's feed."""
        from flask_socketio import join_room
        zone_id = data.get("zone_id")
        if zone_id:
            join_room(f"zone_{zone_id}")
            logger.debug("Client subscribed to zone_%s", zone_id)

    @socketio.on("unsubscribe_zone")
    def on_unsubscribe(data):
        from flask_socketio import leave_room
        zone_id = data.get("zone_id")
        if zone_id:
            leave_room(f"zone_{zone_id}")

    @socketio.on("subscribe_alerts")
    def on_subscribe_alerts():
        """Subscribe to city-wide alert broadcasts."""
        from flask_socketio import join_room
        join_room("alerts_global")
