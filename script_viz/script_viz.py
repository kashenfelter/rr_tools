#! /opt/local/bin/python2.7
"""
The above line is for Mac OSX. If you are running on linux, you may need:
/usr/bin/env python

Jacqueline Kory Westlund
October 2017

The MIT License (MIT)

Copyright (c) 2017 Personal Robots Group

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import argparse  # For getting command line args.
import os.path  # For basename function.
import toml  # For reading the study config file.
import pygraphviz as pgv  # For making the graph!


def make_graph(sconfig, script, mapping, script_name):
    """ Iterate through the script and make a graph of conversation flow. """
    graph = pgv.AGraph(directed=True, strict=False,
                       label="Conversation flow for " + script_name)
    # Set up defaults.
    graph.node_attr["shape"] = "box"
    graph.node_attr["style"] = "filled"
    graph.node_attr["fillcolor"] = "snow2"
    graph.node_attr["color"] = "black"
    graph.edge_attr["color"] = "black"

    # Track the previous node in case we need to connect to it.
    prev_nodes = []
    # Keep counters for questions and animations so we make subtrees instead
    # of looping back when phrases are repeated. The goal is to see the
    # conversation flow, not the total use of each phrase, so this makes sense
    # here.
    qcounter = -1
    acounter = -1

    # Iterate through the script.
    # There are only two kinds of lines we care about for making the graph:
    # ROBOT DO stuff lines and QUESTION lines. Skip all other lines.
    #
    # ROBOT DO -> ROBOT DO: connect directly
    # ROBOT DO -> QUESTION: get question from toml, connect to it
    # map out QUESTION: question, prompts, responses
    # QUESTION -> ROBOT DO: last things robot says in question connect
    for line in script:
        # For ROBOT DO lines, add nodes for the speech or the animations.
        if "ROBOT\tDO" in line:
            # We should parse this line. Split lines on tabs.
            elements = line.strip().split("\t")

            # Line should be "ROBOT DO thing".
            if len(elements) != 3:
                print "Error: ROBOT DO line has wrong number of elements: " \
                      "{}".format(line)
                continue

            node = None
            if elements[2].isupper():
                # Make an animation node.
                acounter += 1
                node = add_animation_node(graph, elements[2], acounter)
            else:
                # Make a speech node.
                node = add_speech_node(
                    graph, elements[2], "", mapping,
                    get_speech_animations(elements[2], sconfig))

            # Add an edge back to any previous nodes that led to this one.
            for prev_node in prev_nodes:
                if not graph.has_edge(prev_node, node):
                    graph.add_edge(prev_node, node)
            # Save this as the latest node in the tree.
            prev_nodes = [node]

        # For QUESTION lines...
        if "QUESTION" in line:
            qcounter += 1
            qtag = "_q" + str(qcounter)
            # Parse line, split on tabs.
            elements = line.strip().split("\t")

            # Line should be "QUESTION name_of_question"
            if len(elements) != 2:
                print "Error: QUESTION line has wrong number of elements: " \
                      "{}".format(line)
                continue

            # Get question from the script config file and make a speech node.
            if "questions" not in sconfig:
                print "ERROR: No questions present in script config!"
                continue
            if elements[1] not in sconfig["questions"]:
                print "ERROR: Question \"{}\" not in script config!".format(
                    elements[1])
                continue

            question = "[no speech]" if sconfig["questions"][elements[1]][
                "question"] == "" else sconfig["questions"][elements[1]][
                    "question"]
            question_node = add_question_node(graph, question, qtag, mapping)

            # Add an edge back to any previous nodes that led to this one.
            for prev_node in prev_nodes:
                if not graph.has_edge(prev_node, question_node):
                    graph.add_edge(prev_node, question_node)
            # Reset previous node list because anything after the question
            # should only connect back to the question.
            prev_nodes = []

            # Add question responses and prompts.
            timeout_prompts = []
            if "timeout_prompts" not in sconfig["questions"][elements[1]]:
                print "No timeout_prompts for question \"{}\", checking for " \
                      "general timeout_prompts...".format(elements[1])
                if "timeout_prompts" not in sconfig:
                    print "Error: No timeout_prompts specified!"
                else:
                    timeout_prompts = sconfig["timeout_prompts"]
            else:
                timeout_prompts = sconfig["questions"][elements[1]][
                    "timeout_prompts"]

            max_attempts = []
            if "max_attempt" not in sconfig["questions"][elements[1]]:
                print "No max_attempts for question \"{}\", checking for " \
                      "general max_attempts...".format(elements[1])
                if "max_attempt" not in sconfig:
                    print "Error: No max_attempt responses specified!"
                else:
                    max_attempts = sconfig["max_attempt"]
            else:
                max_attempts = sconfig["questions"][elements[1]]["max_attempt"]

            user_input = []
            if "user_input" not in sconfig["questions"][elements[1]]:
                print "Error: No user input specified for question \"{}\" " \
                      "in script config!".format(elements[1])
            else:
                user_input = sconfig["questions"][elements[1]]["user_input"]

            # The paths through a question are:
            #   question -> user response -> robot response
            #   question -> prompt -> user response -> robot response
            #   question -> prompt -> prompt -> user response -> robot response
            #   question -> prompt -> prompt -> max attempt
            #
            # Then, for all of the above, connect to the next script line:
            #   robot response -> next line
            #   max attempt -> next line

            # Connect question -> prompt.
            prompt_nodes = []
            for tprompt in timeout_prompts:
                prompt = "[no speech]" if tprompt == "" else tprompt
                # Make a node.
                prompt_node = add_speech_node(
                    graph, prompt, qtag, mapping,
                    get_speech_animations(prompt, sconfig))
                # Connect to the question.
                if not graph.has_edge(question_node, prompt_node):
                    graph.add_edge(question_node, prompt_node)
                # Add to list of prompt nodes.
                prompt_nodes.append(prompt_node)

            # Connect prompt -> prompt.
            for prompt_node1 in prompt_nodes:
                for prompt_node2 in prompt_nodes:
                    if not graph.has_edge(prompt_node1, prompt_node2):
                        graph.add_edge(prompt_node1, prompt_node2)

            # Connect prompt -> max attempt.
            for maxt in max_attempts:
                mat = "[no speech]" if maxt == "" else maxt
                # Make a node.
                mat_node = add_speech_node(
                    graph, mat, qtag, mapping,
                    get_speech_animations(mat, sconfig))
                # Connect to each prompt.
                for prompt_node in prompt_nodes:
                    if not graph.has_edge(prompt_node, mat_node):
                        graph.add_edge(prompt_node, mat_node)
                # Add to list of previous nodes to connect the next line to,
                # i.e., save as the latest nodes in the conversation tree.
                prev_nodes.append(mat_node)

            # Connect user responses and robot responses.
            count = 0
            for response_option in user_input:
                # Make a node.
                user_node = add_user_node(graph, elements[1],
                                          response_option["user_responses"],
                                          count, qtag)

                # Connect question -> user response
                if not graph.has_edge(question_node, user_node):
                    graph.add_edge(question_node, user_node, color="red3")
                count += 1

                # Connect prompt -> user response
                for prompt_node in prompt_nodes:
                    if not graph.has_edge(prompt_node, user_node):
                        graph.add_edge(prompt_node, user_node, color="red3")

                # Connect user response -> robot response
                for rresponse in response_option["robot_responses"]:
                    # Make a node for each robot response.
                    response = "[no speech]" if rresponse == "" else rresponse
                    robot_node = add_speech_node(
                        graph, response, qtag, mapping,
                        get_speech_animations(response, sconfig))
                    # Connect to the user response.
                    if not graph.has_edge(user_node, robot_node):
                        graph.add_edge(user_node, robot_node, color="red3")

                    # Add robot responses to the list of previous nodes to
                    # connect the next line to, i.e., save these as latest
                    # nodes in the conversation tree.
                    prev_nodes.append(robot_node)

        graph.write("graph.dot")
        graph.layout()
        graph.draw("graph-dot.png", prog="dot")


def get_speech_animations(name, config):
    """ Get the animations that get played with the given audio. """
    anims = []
    if "audio" not in config:
        print "ERROR: No audio present in script config!"
    elif name not in config["audio"]:
        print "WARNING: No animations set for audio \"{}\" in " \
            "script config.".format(name)
    else:
        for anim in config["audio"][name]["animations"]:
            anims.append(anim["anim"])
    return anims


def add_animation_node(graph, name, tag):
    """ Add an animation node with appropriate styling. """
    print "Adding animation node \"{}\"...".format(name)
    graph.add_node(name + "_a" + str(tag), label=name, shape="trapezium",
                   fillcolor="lightcyan2")
    return graph.get_node(name + "_a" + str(tag))


def add_user_node(graph, name, response, user_tag, question_tag):
    """ Add a user response node with appropriate styling. """
    print "Adding node \"USER {}{}\"...".format(name, user_tag)
    label = "[ANY]" if response[0] == "" else ",".join(response)
    graph.add_node("USER " + name + str(user_tag) + question_tag, color="red3",
                   fillcolor="pink2", shape="oval", label=label)
    return graph.get_node("USER " + name + str(user_tag) + question_tag)


def add_question_node(graph, name, tag, mapping):
    """ Add a node to the graph, style, and handle errors. """
    try:
        print "Adding question node \"{}\"...".format(name)
        graph.add_node(name + tag, label=mapping[name], color="slateblue3",
                       fillcolor="lavender", shape="diamond")
    except KeyError:
        try:
            graph.add_node(name + tag, label=name, color="sienna2",
                           fillcolor="goldenrod1", shape="diamond")
            print "WARNING: \"{}\" is not in the mapping file!".format(name)
        except KeyError:
            print "\t\"{}\" is a duplicate node. Not adding.".format(name)
    return graph.get_node(name + tag)


def add_speech_node(graph, name, tag, mapping, anims):
    """ Add a node to the graph, style, and handle errors. """
    yellow = False
    try:
        label = mapping[name]
    except KeyError:
        print "WARNING: \"{}\" is not in the mapping file!".format(name)
        label = name
        # Color the node yellow if the audio transcript wasn't found.
        yellow = True

    # If there are animations, list them below the audio transcript.
    if anims:
        label = "{ " + label + " | { " + " | ".join(anims) + "} }"
    try:
        print "Adding speech node \"{}\"...".format(name)
        graph.add_node(name + tag, shape="record", label=label)
        node = graph.get_node(name + tag)
        # Color the node yellow if the audio transcript wasn't found.
        if yellow:
            node.attr["color"] = "sienna"
            node.attr["fillcolor"] = "goldenrod1"
        if anims:
            node.attr["fillcolor"] = "snow2;0.5:lightcyan2"
            node.attr["gradientangle"] = 270

    except KeyError:
        print "\t\"{}\" is a duplicate node. Not adding.".format(name)
    else:
        return node


def process_mapping(mapfile):
    """ Process the CSV file mapping audio filenames to audio transcriptions so
    we can use it for easy lookups later.
    """
    try:
        with open(mapfile) as fileh:
            maptext = fileh.readlines()
            print "Reading audio to transcript mapping..."
    except IOError as ioe:
        print "Could not read your mapping file \"{}\"! Exiting because we " \
              "need it to create the graph. Error: {}".format(mapfile, ioe)
        exit(1)

    mapping = {}
    # Map file has two lines of header before the content. Only use the rest.
    for line in maptext[2:]:
        elements = line.split("\t")
        # Map file columns:
        # robot, project, filename, text, visemes...
        mapping[elements[2]] = elements[3]
    return mapping


def main():
    """ Main function: Parse args, read in files, make a graph! """
    parser = argparse.ArgumentParser("Given script files and a mapping of " \
                                     "audio file names to audio transcripts," \
                                     " make a graph of the conversation flow!")
    parser.add_argument(type=str, default="", dest="script_config",
                        help="""TOML script config file. """)
    parser.add_argument(type=str, default="", dest="script_file",
                        help="""Main script file.""")
    parser.add_argument(type=str, default="", dest="mapping",
                        help="""CSV file mapping audio file names to the
                        transcript of the audio files.""")
    args = parser.parse_args()
    # TODO add in any repeating scripts or story scripts?

    # Read in TOML script config.
    try:
        with open(args.script_config) as tof:
            script_config = toml.load(tof)
            print "Reading script config..."
    except Exception as exc:  # pylint: disable=broad-except
        print "Could not read your toml study config file \"{}\". Exiting " \
            "because we need it to continue. Error: {}".format(
                args.script_config, exc)
        exit(1)

    # Read in main script file.
    try:
        with open(args.script_file) as fileh:
            script = fileh.readlines()
            print "Reading main script..."
    except IOError as ioe:
        print "Could not read your script file \"{}\"! Exiting because we " \
              "need it to create the graph. Error: {}".format(args.script_file,
                                                              ioe)
        exit(1)

    # Read the audio-transcript csv mapping file.
    mapping = process_mapping(args.mapping)

    # We have data: make a graph!
    make_graph(script_config, script, mapping, os.path.basename(args.script_file))


if __name__ == "__main__":
    main()
