#!/usr/bin/env python3

import argparse, json, os, signal, subprocess, time

REPLSET_CONFIG = json.loads(
'''
{
    "version": 1,
    "processes": [
        {
            "name": "foo1",
            "processType": "mongod",
            "version": "4.0.9",
            "featureCompatibilityVersion": "4.0",
            "args2_6": {
                "systemLog": {
                    "destination": "file",
                    "path": "/tmp/mms-automation/logs/foo1_run.log"
                },
                "storage": {
                    "dbPath": "/tmp/mms-automation/data/foo1"
                },
                "net": { 
                    "port": 5000
                },
                "replication": {
                    "replSetName": "rs1"
                }
            } 
        },
        {
            "name": "foo2",
            "processType": "mongod",
            "version": "4.0.9",
            "featureCompatibilityVersion": "4.0",
            "args2_6": {
                "systemLog": {
                    "destination": "file",
                    "path": "/tmp/mms-automation/logs/foo2_run.log"
                },
                "storage": {
                    "dbPath": "/tmp/mms-automation/data/foo2"
                },
                "net": { 
                    "port": 5001
                },
                "replication": {
                    "replSetName": "rs1"
                }
            } 
        },
        {
            "name": "foo3",
            "processType": "mongod",
            "version": "4.0.9",
            "featureCompatibilityVersion": "4.0",
            "args2_6": {
                "systemLog": {
                    "destination": "file",
                    "path": "/tmp/mms-automation/logs/foo3_run.log"
                },
                "storage": {
                    "dbPath": "/tmp/mms-automation/data/foo3"
                },
                "net": { 
                    "port": 5002
                },
                "replication": {
                    "replSetName": "rs1"
                }
            } 
        }
    ],
    "replicaSets": [
        {
            "_id": "rs1",
            "members": [
                {
                    "_id": 0,
                    "host": "foo1"
                },
                {
                    "_id": 1,
                    "host": "foo2"
                },
                {
                    "_id": 2,
                    "host": "foo3"
                }
            ]
        }
    ],
    "options": {
        "downloadBase": "/tmp/mms-automation/test/versions"
    },
    "mongoDbVersions": [{
        "name": "4.0.9",
        "builds": [{
            "architecture": "amd64",
            "platform": "linux", 
            "url": "https://fastdl.mongodb.org/linux/mongodb-linux-x86_64-4.0.9.tgz",
            "gitVersion": "fc525e2d9b0e4bceff5c2201457e564362909765",
            "bits" : 64
        }]
    }]
}
'''
)

TOPOLOGIES = {
    'replset': REPLSET_CONFIG,
}

def parse_arguments():
    '''Parse the command-line arguments passed to the script and return the args object.'''
    parser = argparse.ArgumentParser(description='Live Failure Testing Script')
    parser.add_argument(
       '--agent-config',
       default='agent-config.json',
       help='location of the config file to be used by the automation agent')
    parser.add_argument(
        '--agent-log',
        default='agent.log',
        help="location of the automation agent's log file")
    parser.add_argument(
        '--topology',
        default='replset',
        choices={ 'replset', 'sharded' },
        help='location of the config file specifying the topology of the cluster')
    parser.add_argument(
        '--sleep',
        type=int,
        default=3,
        help='duration (in seconds) to sleep between node restarts')
    parser.add_argument(
        '--tombstone-file',
        help='create a tombstone file at the given path upon completion of the scenario')
    
    return parser.parse_args()
    
def goal_state_message(num_processes):
    return f"All {num_processes} Mongo processes are in goal state"
    
def update_topology(topology, agent_config):
    with open(agent_config, 'w') as agent_file:
        json.dump(topology, agent_file)

def wait_for_agent_goal_state(agent_log, num_processes, msg, start_from=0):
    '''Wait for the automation agent to reach the goal state and returns the point in 
       the file to resume from the next time this function is called.
    '''

    goal_state = goal_state_message(num_processes)
    curr_loc = start_from
    
    while True:
        print(msg)
        
        with open(agent_log) as log_file:
            log_file.seek(curr_loc)

            new_content = log_file.read()
            curr_loc = log_file.tell()
            
            if goal_state in new_content:
                break            
            
        time.sleep(2)
                
    return curr_loc
    
def start_automation_agent(agent_config, agent_log, topology):
    '''Initialize the automation agent and wait for the initial topology to be ready.
       
       Returns the automation agent PID and the location in the agent log file to
       resume from.'''
       
    print('Launching the automation agent...')
    
    update_topology(topology, agent_config)
    
    with open(agent_log, 'a') as log_file:
        pid = subprocess.Popen(
                    ['mongodb-mms-automation-agent', '-cluster', agent_config], 
                    stdout=log_file,
                    stderr=subprocess.STDOUT).pid
            
    resume_from = wait_for_agent_goal_state(
                      agent_log, 
                      len(topology['processes']), 
                      'Waiting for cluster to come online...')
    
    return pid, resume_from
    
def kill_and_wait(pid):
    os.kill(pid, signal.SIGINT)
    
    while True:
        finished_pid, _ = os.wait()
        
        if finished_pid == pid:
            return
            
        time.sleep(2)
 

def finish(agent_pid, agent_config, agent_log, topology, resume_from, tombstone_file):
    '''Perform final cleanup steps and create the tombstone file if necessary.'''
    
    print('Scenario complete.')
    
    for process in topology['processes']:
        process['disabled'] = True
    
    update_topology(topology, agent_config) 
    wait_for_agent_goal_state(
        agent_log,
        len(topology['processes']),
        'Waiting for cluster to shut down...',
        start_from=resume_from)

    print('Killing the automation agent.')
    kill_and_wait(agent_pid)
   
    os.remove(agent_log)
    os.remove(agent_config)
    
    if tombstone_file:
        with open(tombstone_file, 'w') as f:
            f.write('Scenario completed')
    
def main():
    args = parse_arguments()

    topology = TOPOLOGIES[args.topology]
    agent_pid, resume_from = start_automation_agent(args.agent_config, args.agent_log, topology)
    
    finish(agent_pid, args.agent_config, args.agent_log, topology, resume_from, args.tombstone_file)
    
    
main()