import glob
import json
import os
import yaml

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
				if filename in ("output.json", "output-deployment.json", "output-service.json"):
					continue
				path = os.path.join(root, filename)
				if filename.endswith(".yaml"):
					self.files.append(path)
				elif filename.endswith(".json"):
					self.files.append(path)

	def scanobjects(self, objects):
		for obj in objects:
			if "kind" in obj:
				if obj["kind"] == "Namespace":
					ns = obj["metadata"]["name"]
					print("# convert namespace {} to label".format(ns))
					self.label = ns
				elif obj["kind"] in ("Deployment", "DeploymentConfig"):
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
				elif obj["kind"] in ("BuildConfig", "Build", "ImageStream", "Route", "Pod", "ReplicationController"):
					print("# ignore {}".format(obj["kind"]))
				elif obj["kind"] == "List":
					print("# recurse into list")
					for item in obj["items"]:
						item["*origin*"] = obj["*origin*"]
					self.scanobjects(obj["items"])
				else:
					raise Exception("Unknown kind {}".format(obj["kind"]))

				if obj["kind"] in ("Deployment", "DeploymentConfig", "Service"):
					if has_keychain(obj, ["metadata", "namespace"]):
						ns = obj["metadata"]["namespace"]
						print("# convert namespace {} to label".format(ns))
						if obj["kind"] == "Deployment":
							obj["spec"]["template"]["metadata"]["labels"]["namespaceLabel"] = ns
						elif obj["kind"] == "Service":
							if has_keychain(obj, ["metadata", "labels"]):
								obj["metadata"]["labels"]["namespaceLabel"] = ns
						del obj["metadata"]["namespace"]

	def parse(self, output="output"):
		for filename in self.files:
			if filename.endswith(".yaml"):
				self.objects.append(yaml.load(open(filename)))
			elif filename.endswith(".json"):
				self.objects.append(json.load(open(filename)))
			self.objects[-1]["*origin*"] = filename

		self.scanobjects(self.objects)

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

		os.makedirs(output, exist_ok=True)

		print("# rewrite into output-*.json")
		f = open(os.path.join(output, "output-deployment.json"), "w")
		json.dump(self.basedeployment, f, indent=2, sort_keys=True)
		f.close()

		for exclusion in exclusions:
			for obj in self.objects:
				if "*origin*" in obj and obj["*origin*"] == exclusion:
					containers = []
					for container in self.containers:
						if self.originfiles[container["name"]] == exclusion:
							containers.append(container)
					if has_keychain(obj, ["spec", "template", "spec"]):
						obj["spec"]["template"]["spec"]["containers"] = containers
					else:
						print("# warning (bug!): not updating containers assignment, probably due to list object")
					del obj["*origin*"]
					f = open(os.path.join(output, os.path.basename(exclusion)), "w")
					json.dump(obj, f, indent=2, sort_keys=True)
					f.close()

		ports = []
		for obj in self.objects:
			if "kind" in obj:
				if obj["kind"] == "Service":
					if has_keychain(obj, ["spec", "selector"]):
						labels = obj["spec"]["selector"]
						match = False
						for label in labels:
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
