from flask import Blueprint, jsonify

from ..extensions import db
from ..models import Device

bp = Blueprint("devices", __name__)


@bp.get("")
def list_devices():
    return jsonify(data=[d.to_dict() for d in Device.query.order_by(Device.id)])


@bp.get("/<int:device_id>")
def get_device(device_id):
    device = db.get_or_404(Device, device_id)
    return jsonify(device.to_dict())
