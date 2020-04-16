def formattedBranchName = BRANCH_NAME.replaceAll('/', '::')

def repoName = "relayr/kafka-python"

node('jenkins-neokami-slave', {

    dockerTag = "${env.BRANCH_NAME}_${env.BUILD_NUMBER}"

    properties([
            buildDiscarder(
                    logRotator(
                            artifactDaysToKeepStr: '',
                            artifactNumToKeepStr: '20',
                            daysToKeepStr: '',
                            numToKeepStr: '20'
                    )
            ),
            pipelineTriggers([[$class: 'GitHubPushTrigger']])
    ])

    timestamps {
        withEnv(['FORMATTED_BRANCH_NAME=' + formattedBranchName,
                 'BUILD_NUMBER=' + env.BUILD_NUMBER]) {

            stage ('Preparing VirtualEnv') {
                cleanWs()
                checkout scm

                if (!fileExists('.env')){
                    echo 'Creating virtualenv ...'
                    sh 'virtualenv -p python3.6 .env'
                }
            }

            stage('Install') {
                sh """
                    ./.env/bin/pip install .[dev]
                """
            }

            stage('Tests + Coverage') {
                sh """
                    . .env/bin/activate
                    pytest -k 'not consumer_integration' --cov=kafka --cov-report xml
                """
            }

//             stage('Distribute Wheel') {
//                 // if not master, then substitute version with version-branch-build tag
//                 if (env.BRANCH_NAME != "master") {
//                     sh """
//                         sed -i 's/_VERSION = "\\(.*\\)"/_VERSION = "\\1-${env.BRANCH_NAME}--build-${env.BUILD_NUMBER}"/g' setup.py
//                     """
//                 }
//
//                 sh """
//                     . .env/bin/activate
//                     python setup.py bdist_wheel
//                 """
//
//                 archiveArtifacts artifacts: 'dist/*'
//
//                 sh """
//                     . .env/bin/activate
//                     pip install twine
//                     twine upload --repository pypicloud --skip-existing dist/*
//                 """
//             }

        }
    }
})
