#!/usr/bin/env python3

import glob
import json
import os
import yaml
import sys
import shutil

def has_keychain(d, keychain):
	if keychain[0] in d:
		if len(keychain) == 1:
			return True
		return has_keychain(d[keychain[0]], keychain[1:])
	return False

class DescriptorRewriter:
	def __init__(self):
		self.files = []
		self.objects = []
		self.label = None
		self.containers = []
		self.basedeployment = None
		self.baseservice = None
		self.ports = []
		self.originfiles = {}
		self.labels = []

	def scandir(self, rootdir):
		if rootdir.endswith(".yaml"):
			self.files.append(rootdir)
		elif rootdir.endswith(".json"):
			self.files.append(rootdir)
		for root, dirs, files in os.walk(rootdir):
			for filename in files:
				if filename == "output.json":
					continue
				path = os.path.join(root, filename)
				#print(path)
				if filename.endswith(".yaml"):
					self.files.append(path)
				elif filename.endswith(".json"):
					self.files.append(path)

	def parse(self):
		for filename in self.files:
			#print("/p", filename)
			if filename.endswith(".yaml"):
				self.objects.append(yaml.load(open(filename)))
			elif filename.endswith(".json"):
				self.objects.append(json.load(open(filename)))
			self.objects[-1]["*origin*"] = filename

		#print(self.objects)
		for obj in self.objects:
			if "kind" in obj:
				if obj["kind"] == "Namespace":
					ns = obj["metadata"]["name"]
					print("# convert namespace {} to label".format(ns))
					self.label = ns
				elif obj["kind"] == "Deployment":
					if not self.basedeployment:
						self.basedeployment = obj
					if has_keychain(obj, ["spec", "template", "spec", "containers"]):
						containers = obj["spec"]["template"]["spec"]["containers"]
						self.containers += containers
						for container in containers:
							self.originfiles[container["name"]] = obj["*origin*"]
				elif obj["kind"] == "Service":
					if not self.baseservice:
						self.baseservice = obj
				else:
					raise Exception("Unknown kind {}".format(obj["kind"]))

				if obj["kind"] in ("Deployment", "Service"):
					if has_keychain(obj, ["metadata", "namespace"]):
						ns = obj["metadata"]["namespace"]
						print("# convert namespace {} to label".format(ns))
						if obj["kind"] == "Deployment":
							obj["spec"]["template"]["metadata"]["labels"]["namespaceLabel"] = ns
						elif obj["kind"] == "Service":
							obj["metadata"]["labels"]["namespaceLabel"] = ns
						del obj["metadata"]["namespace"]

		for container in self.containers:
			r = container.setdefault("resources", {})
			l = container["resources"].setdefault("limits", {})
			c = container["resources"]["limits"].setdefault("cpu", "500m")
			if c[-1] == "m":
				c = int(c[:-1])
			else:
				c = int(float(c) * 100)
			c //= 5
			print("# constrain to", c, "millicores")
			container["resources"]["limits"]["cpu"] = "{}m".format(c)

		exclusions = []
		joinedcontainers = []
		for container in self.containers:
			if "ports" in container:
				for port in container["ports"]:
					if "containerPort" in port:
						portnum = port["containerPort"]
						if portnum in self.ports:
							exclusion = self.originfiles[container["name"]]
							exclusions.append(exclusion)
							print("! port conflict", portnum, "excluding", exclusion)
						else:
							self.ports.append(portnum)
							joinedcontainers.append(container)

							for obj in self.objects:
								if obj["*origin*"] == self.originfiles[container["name"]]:
									if has_keychain(obj, ["spec", "template", "metadata", "labels"]):
										labels = obj["spec"]["template"]["metadata"]["labels"]
										for label in labels:
											self.labels.append((label, labels[label]))

		print("# merge", len(joinedcontainers), "out of", len(joinedcontainers) + len(exclusions), "containers into a single deployment")

		self.basedeployment["spec"]["template"]["spec"]["containers"] = joinedcontainers
		self.basedeployment["spec"]["template"]["metadata"]["labels"]["powerSelector"] = "rewritten-app"
		self.basedeployment["metadata"]["name"] = "rewritten-app"
		del self.basedeployment["*origin*"]

		output = "output"

		os.makedirs(output, exist_ok=True)

		print("# rewrite into output.json")
		f = open(os.path.join(output, "output-deployment.json"), "w")
		json.dump(self.basedeployment, f, indent=2, sort_keys=True)
		f.close()

		for exclusion in exclusions:
			#shutil.copy(exclusion, "output")
			##self.originfiles[container["name"]] = obj["*origin*"]
			for obj in self.objects:
				if "*origin*" in obj and obj["*origin*"] == exclusion:
					#print(exclusion)
					containers = []
					for container in self.containers:
						if self.originfiles[container["name"]] == exclusion:
							#print("**", container["name"])
							containers.append(container)
					obj["spec"]["template"]["spec"]["containers"] = containers
					del obj["*origin*"]
					f = open(os.path.join(output, os.path.basename(exclusion)), "w")
					json.dump(obj, f, indent=2, sort_keys=True)
					f.close()

		ports = []
		for obj in self.objects:
			if "kind" in obj:
				if obj["kind"] == "Service":
					#if has_keychain(obj, ["metadata", "labels"]):
					#	labels = obj["metadata"]["labels"]
					if has_keychain(obj, ["spec", "selector"]):
						labels = obj["spec"]["selector"]
						match = False
						for label in labels:
							#print("# label in", obj["metadata"]["name"], ":", label, "=", labels[label])
							for slabel in self.labels:
								if slabel[0] == label and slabel[1] == labels[label]:
									print("# rewrite label selector", label)
									match = True

					if match:
						ports += obj["spec"]["ports"]
					else:
						f = open(os.path.join(output, os.path.basename(obj["*origin*"])), "w")
						del obj["*origin*"]
						json.dump(obj, f, indent=2, sort_keys=True)
						f.close()

		del self.baseservice["*origin*"]
		self.baseservice["spec"]["selector"] = {"powerSelector": "rewritten-app"}
		self.baseservice["spec"]["ports"] = ports
		self.baseservice["metadata"]["name"] = "rewritten-service"

		f = open(os.path.join(output, "output-service.json"), "w")
		json.dump(self.baseservice, f, indent=2, sort_keys=True)
		f.close()

dirs = ["."]
if len(sys.argv) > 1:
	dirs = sys.argv[1:]

dr = DescriptorRewriter()
for dirname in dirs:
	dr.scandir(dirname)
dr.parse()
