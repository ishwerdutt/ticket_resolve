"""Tool registry: maps tool names to their OpenAI function schemas."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Get details of a customer's order including items, status, and dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "The order UUID or order number"}
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "track_shipment",
            "description": "Get live shipment tracking status for an order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"}
                },
                "required": ["order_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_policy",
            "description": "Search ThreadNest store policies including Return Policy, Shipping Policy, Cancellation & Modification Policy, Warranty & Quality Guarantee, and FAQs. Always call this when answering customer policy questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The policy question or topic to search"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_refund_eligibility",
            "description": "Check if an order is eligible for a refund and what the maximum amount is.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "reason": {"type": "string", "description": "Reason for refund (e.g. 'damaged', 'wrong_item', 'not_as_described')"}
                },
                "required": ["order_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_refund",
            "description": "Create a refund for a delivered order. Only call after checking eligibility.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "amount": {"type": "number", "description": "Refund amount in INR"},
                    "reason": {"type": "string"}
                },
                "required": ["order_id", "amount", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_replacement",
            "description": "Create a replacement order for a wrong or damaged item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "item_id": {"type": "string", "description": "The order_item UUID to replace"},
                    "reason": {"type": "string"}
                },
                "required": ["order_id", "item_id", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_address",
            "description": "Update the delivery address for an order that has not yet been dispatched.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "new_address": {
                        "type": "object",
                        "properties": {
                            "line1": {"type": "string"},
                            "line2": {"type": "string"},
                            "city": {"type": "string"},
                            "state": {"type": "string"},
                            "pincode": {"type": "string"}
                        },
                        "required": ["line1", "city", "state", "pincode"]
                    }
                },
                "required": ["order_id", "new_address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_ticket",
            "description": "Create a support ticket for escalation or complex issues requiring human review.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Brief summary of the issue"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]}
                },
                "required": ["summary", "priority"]
            }
        }
    }
]
