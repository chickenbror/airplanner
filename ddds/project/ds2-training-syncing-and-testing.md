### Intro

This document will guide you on your way to set up your access to train Rasa models, sync your DDD (Dialogue Domain Description) files and Rasa models with the Kubernetes cluster. And interact with your dialogue apps using the Tala SDK.


### Requirements

Set up your access to the Kubernetes cluster as detailed in the other file `ds2-practical-preparations.md`


### Syncing your local DDD files to the Kubernetes cluster with Okteto

1. Log into "eduserv" via SSH.
`ssh -p 62266 -Y -L 16443:127.0.0.1:16443 gusXXXXXX@eduserv.flov.gu.se`
You just need to start this ssh session and let it run on the background. Run the rest of the steps in your own machine as the requirements specified above are not installed in the eduserv.

2. (In your local machine) To be able to test and interact with your dialogue apps running in the Kubernetes cluster, you need to sync your local files using Okteto in three different command consoles. Each of these Okteto instances will sync the files specified below with deployments that run each different parts of your code:

  - Your "http_service.py" will be synced to the "http-service" deployment in your namespace.
    1. Go into the "ddds/DDD_NAME/http-service/" folder
    2. Run in your console:
    `okteto up --namespace gusXXXXXX`
    This starts an Okteto session that syncs your files in that folder (except the ones specified in the ".stignore" file) with the "http-service" deployment in your namespace. It also takes care of running the http-service, so you just need to wait it to load.
    When you see console outputs such as:
      `{"event": "Booting worker with pid: 111", "level": "info", "logger": "gunicorn.error", "time": "2021-08-25T12:37:32.497834Z"}`
    Then it's loaded.
    If you change something in your http_service.py you don't need to worry, it will reload the file with the new changes automatically.
      IMPORTANT! If for some reason `okteto up` fails, which we have seen happening a bunch of times, read the note at the bottom of the file.

  - Your DDD files will be synced to the "tdm" deployment in your namespace.
    1. Go into the "ddds/DDD_NAME/" folder
    2. Run in your console:
    `okteto up --namespace gusXXXXXX`
    This starts an Okteto session that syncs your files in that folder (except the ones specified in the ".stignore" file) with the "tdm" deployment in your namespace.
      IMPORTANT! If for some reason `okteto up` fails, which we have seen happening a bunch of times, read the note at the bottom of this file.
    3. When the syncing has finished, you will be in a command console inside the deployment with which you're synced. There you have to use the TDM library to build and serve your DDD so you can test and interact with it.
    ```
    tdm build; tdm serve eng --log-to-stdout --log-level INFO
    ```
    You will see that the last command generated the url "http://localhost:9090/interact". You don't have to open it in a browser, but you will use it for test and interact with your DDDs. You will see it further down.
      IMPORTANT: If you change something in your DDD (not HTTP Service), you need to stop (ctrl+C) the `tdm serve` and repeat the command above!


### Test and interact with your DDDs using the Tala SDK

(Everything here is run your local machine)

NOTE: If you want to test the DDD and you don't have a Rasa model trained yet, change the URL "http://pipeline/interact" to "http://tdm/interact" in the commands below.

1. OK, you can (finally) test your DDD with Tala. For that, in another console (yes, we know, lots of them), go into "ddds/DDD_NAME/" and run:
`kubectl exec -n gusXXXXXX -it deploy/tdm -- tala test http://pipeline/interact /okteto/DDD_NAME/test/interaction_tests_eng.txt`

  You can also run an individual test in the file with the argument `-t`. For instance:
  `kubectl exec -n gusXXXXXX -it deploy/tdm -- tala test http://pipeline/interact /okteto/DDD_NAME/test/interaction_tests_eng.txt -t "call (incremental)"`

2. If you want to interact with your DDD via text interface, you can do it with Tala as well.
`kubectl exec -n gusXXXXXX -it deploy/tdm -- tala interact http://pipeline/interact`

3. Once you're done and you don't want to sync your local files anymore, don't forget to exit all the cluster deployments (the three consoles in which you have `okteto up` running). To do so, stop (ctrl+C) the commands running in the deployments. This will exit the consoles running in the deployments "nlu-rasa" and "http-service". To exit the "tdm" one, do ctrl+C followed by ctrl+D.
When you're in your local machine, I recommend you to run the following command in all the three consoles to close the okteto session:
  `okteto down -v --namespace gusXXXXXX`


### Training Rasa models

1. We need to generate data to train a Rasa model based on what you have in your "grammar_eng.xml" file.
In your console of your local machine go into the "ddds/DDD_NAME/" directory (the one that contains "backend.config.hjson") and run e.g.:
`tala generate rasa DDD_NAME eng > ../../rasa-nlu/training-data-eng.yml`
This will create the "training-data-eng.yml" file, which contains the intents and entries. The file will be in the "rasa-nlu/" directory.

2. Log into to "mltgpu" via SSH. However, you need to tunnel a port to your localhost. This is the port that you will use to train your rasa model. For instance, let's take the port 5010:
`ssh -p 62266 -Y -L 5010:127.0.0.1:5010 gusXXXXXX@mltgpu.flov.gu.se`

    NOTE: You can replace port 5010 with almost any other port you want if that port doesn't work. Just take into account which port you are tunneling for the next steps.

3. (In mltgpu) Here you need to use Rasa 2.4.3. In order to do so, we have prepared a virtual environment that you should be able to use with: 
`module load lt2319`
    NOTE: you can unload it at any time with `module unload lt2319`

4. (In mltgpu) Run the following to start a Rasa server (see that it uses the port 5010 that we have tunneled earlier):
`python3 -m rasa run --enable-api -vv -p 5010`
    Wait till the logs say: "INFO     root  - Rasa server is up and running"

5. (In your local machine) Go to the "rasa-nlu/" directory and run the "train.py" script. Example command with arguments:
`python3 train.py eng -u http://127.0.0.1:5010/model/train`
    This script trains a model with your data in the Rasa server you're running in mltgpu. After training, the model is downloaded to your local machine.

6. (In mltgpu) When the training is done you can just stop the Rasa server (ctrl+C) and close your SSH session to mltgpu (ctrl+D).


### Sync Rasa models with Okteto

1. Go into the "rasa-nlu/" folder
2. Run in your console:
`okteto up --namespace gusXXXXXX`
  This starts an Okteto session that syncs your files in that folder (except the ones specified in the ".stignore" file) with the "nlu-rasa" deployment in your namespace. It also takes care of running the rasa model, so you just need to wait it to load (it normally takes 1-3 minutes).
  When you see the console output `INFO     root  - Rasa server is up and running.`, then the model is loaded.
    NOTE: Don't worry about the CUDA error, it's expected (`E tensorflow/stream_executor/cuda/cuda_driver.cc:351] failed call to cuInit: UNKNOWN ERROR (303)`). It will continue loading the model after the error.
    IMPORTANT! If for some reason `okteto up` fails, which we have seen happening a bunch of times, read the note at the bottom of the file.


### NOTE about Okteto
Run `okteto down -v` if for some reason `okteto up` fails. If it keeps failing after you've tried `down` and then `up` again about 3 times, contact José.