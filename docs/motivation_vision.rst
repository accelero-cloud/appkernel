Why did we built this?
----------------------
* We had the need to build a myriad of small services in our daily business, ranging from data-aggregation pipelines, to housekeeping services and other process automation services. These do share similar requirements and the underlying infrastructure needed to be rebuilt and tested over and over again. The question arose: what if we avoid spending valuable time on the boilerplate and focus only on the fun part?

* Often time takes a substantial effort to make a valuable internal hack or proof of concept presentable to customers, until it reaches the maturity in terms reliability, fault tolerance and security. What if all these non-functional requirements would be taken care by an underlying platform?

* There are several initiatives out there (Flask Admin, Flask Rest Extension and so), which do target parts of the problem, but they either need substantial effort to make them play nice together, either they feel complicated and uneasy to use. We wanted something simple and beautiful, which we love working with.

* These were the major driving question, which lead to the development of App Kernel.