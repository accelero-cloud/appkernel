Why did we build this?
----------------------

* We needed to build a large number of small services in our daily work — data-aggregation pipelines, housekeeping services, process automation, and the like. They all share the same infrastructure requirements, and rebuilding that infrastructure from scratch every time is neither fun nor a good use of anyone's afternoon.

* Turning a valuable internal prototype into something presentable to customers takes a disproportionate amount of effort. Reliability, fault tolerance, and security are non-negotiable, but they shouldn't require weeks of work before you can demo anything. What if all those non-functional requirements were handled by the platform itself?

* Plenty of libraries address *parts* of this problem, but wiring them together tends to be fiddly and the result often feels more like archaeology than engineering. We wanted something simple and coherent that we'd actually enjoy using.

* Those questions led to AppKernel.

How does it help you?
----------------------

**We did the heavy lifting so you can focus on the things that matter.**

We believe you want to be delivering business value from day one — not configuring middleware. So we made the hard choices on your behalf: database access, serialisation, validation, security, rate limiting, and inter-service communication are all covered. Your job is to describe your domain and let AppKernel handle the rest.

**Lay back, fasten your seatbelts, and enjoy the ride.**
