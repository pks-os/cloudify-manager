

from cloudify.decorators import workflow
from cloudify.workflows.tasks_graph import TaskDependencyGraph, forkjoin


@workflow
def install(ctx, **kwargs):

    graph = TaskDependencyGraph(ctx)
    send_event_creating_tasks = {node.id: node.send_event('Creating node')
                                 for node in ctx.nodes}
    set_state_creating_tasks = {node.id: node.set_state('creating')
                                for node in ctx.nodes}
    set_state_started_tasks = {node.id: node.set_state('started')
                               for node in ctx.nodes}

    # Create node linear task sequences
    for node in ctx.nodes:
        sequence = graph.sequence()

        sequence.add(
            node.set_state('initializing'),
            forkjoin(
                set_state_creating_tasks[node.id],
                send_event_creating_tasks[node.id]
            ),
            node.execute_operation('cloudify.interfaces.lifecycle.create'),
            node.set_state('created'),
            forkjoin(*relationship_operations(
                node,
                'cloudify.interfaces.relationship_lifecycle.preconfigure')),
            forkjoin(
                node.set_state('configuring'),
                node.send_event('Configuring node')),
            node.execute_operation('cloudify.interfaces.lifecycle.configure'),
            node.set_state('configured'),
            forkjoin(*relationship_operations(
                node,
                'cloudify.interfaces.relationship_lifecycle.postconfigure')),
            forkjoin(
                node.set_state('starting'),
                node.send_event('Starting node')),
            node.execute_operation('cloudify.interfaces.lifecycle.start'))

        if _is_host_node(node):
            sequence.add(*_host_post_start(node))

        sequence.add(
            set_state_started_tasks[node.id],
            forkjoin(*relationship_operations(
                node,
                'cloudify.interfaces.relationship_lifecycle.establish')))

    # Create task dependencies based on node relationships
    for node in ctx.nodes:
        for rel in node.relationships:
            node_set_creating = set_state_creating_tasks[node.id]
            node_event_creating = send_event_creating_tasks[node.id]
            target_set_started = set_state_started_tasks[rel.target_id]
            graph.add_dependency(node_set_creating, target_set_started)
            graph.add_dependency(node_event_creating, target_set_started)

    graph.execute()


def relationship_operations(node, operation):
    tasks = []
    for relationship in node.relationships:
        tasks.append(relationship.execute_source_operation(operation))
        tasks.append(relationship.execute_target_operation(operation))
    return tasks


def _is_host_node(node):
    return 'cloudify.types.host' in node.type_hierarchy


def _wait_for_host_to_start(host_node):
        task = host_node.execute_operation(
            'cloudify.interfaces.host.get_state')

        # handler for retrying if get_state returns False
        def get_node_state_handler(tsk):
            return tsk.async_result.get() is False
        task.on_success = get_node_state_handler
        return task


def _host_post_start(host_node):
    tasks = [_wait_for_host_to_start(host_node)]
    if host_node.properties['install_agent'] is True:
        tasks += [
            host_node.send_event('Installing worker'),
            host_node.execute_operation(
                'cloudify.interfaces.worker_installer.install'),
            host_node.execute_operation(
                'cloudify.interfaces.worker_installer.start'),
            host_node.send_event('Installing plugin')]
        for plugin in host_node.plugins_to_install:
            tasks += [
                host_node.send_event('Installing plugin: {0}'
                                     .format(plugin['name'])),
                host_node.execute_operation(
                    'cloudify.interfaces.plugin_installer.install',
                    kwargs={'plugin': plugin})]
        tasks.append(host_node.execute_operation(
            'cloudify.interfaces.worker_installer.restart'))
    return tasks
