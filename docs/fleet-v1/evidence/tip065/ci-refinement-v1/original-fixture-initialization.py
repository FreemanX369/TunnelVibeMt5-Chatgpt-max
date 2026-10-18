stopping = object.__new__(NodeRuntime)
stopping.agent, stopping.dispatcher, stopping.client = (agent, dispatcher, client)
stopping.policy, stopping.config = (fleet_policy(), {'drain_timeout_ms': 1})
stopping._resources = [transport, domains, jobs, dispatcher.principals]
stopping._closed, stopping._stopping, stopping._drain_deadline = (False, False, None)
