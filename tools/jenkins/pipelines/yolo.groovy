pipeline {

    agent { label 'jenkins-jnlp-agent' }

    parameters {
        choice(
            name: 'PRODUCT',
            description: 'Product to deploy',
            choices: ['awx', 'tower']
        )
        choice(
            name: 'SCENARIO',
            description: 'Deployment scenario for Tower',
            choices: ['standalone', 'cluster']
        )
        string(
            name: 'TOWER_FORK',
            description: 'Fork of tower to deploy',
            defaultValue: 'ansible'
        )
        string(
            name: 'TOWER_BRANCH',
            description: 'Branch to use for Tower',
            defaultValue: 'devel'
        )
        string(
            name: 'TOWER_PACKAGING_FORK',
            description: 'Fork of tower-packaging to deploy',
            defaultValue: 'ansible'
        )
        string(
            name: 'TOWER_PACKAGING_BRANCH',
            description: 'Branch to use for tower-packaging',
            defaultValue: 'devel'
        )
        string(
            name: 'TOWER_QA_FORK',
            description: 'Fork of tower-qa. Useful for testing changes to this pipeline.',
            defaultValue: 'ansible'
        )
        string(
            name: 'TOWER_QA_BRANCH',
            description: 'Branch to use for tower-qa',
            defaultValue: 'devel'
        )
        string(
            name: 'TOWERKIT_BRANCH',
            description: 'Branch to use for towerkit',
            defaultValue: 'devel'
        )
        string(
            name: 'RUNNER_FORK',
            description: 'Fork of ansible-runner to deploy (Leave empty to rely on latest RPM)',
            defaultValue: ''
        )
        string(
            name: 'RUNNER_BRANCH',
            description: 'Branch to use for ansible-runner (Leave empty to rely on latest RPM)',
            defaultValue: ''
        )
        booleanParam(
            name: 'BUILD_INSTALLER_AND_PACKAGE',
            description: 'Should the installer and the packages be built as part of this pipeline ?',
            defaultValue: true
        )
        booleanParam(
            name: 'RUN_INSTALLER',
            description: 'Should the installer be run as part of this pipeline ?',
            defaultValue: true
        )
        booleanParam(
            name: 'RUN_TESTS',
            description: 'Should the integration test suite be run as part of this pipeline ?',
            defaultValue: true
        )
        booleanParam(
            name: 'RUN_E2E',
            description: 'Should the e2e test suite be run as part of this pipeline ?',
            defaultValue: true
        )
        booleanParam(
            name: 'RETRY_FAILED_TESTS',
            description: 'Should e2e tests be retried on failure ?',
            defaultValue: true
        )
        string(
            name: 'TESTEXPR',
            description: """\
            Test expression to pass to pytest to select which tests will be run.
            Use "yolo or ansible_integration" (default) to run YOLO.
            Use "test" to run SLOWYO (note that this will use a bigger EC2 instance to run tests quickly if SCENARIO is standalone and RUN_TESTS is checked. Because of that, the deployed instance will always be torn down).
            """,
            defaultValue: 'yolo or ansible_integration'
        )
        string(
            name: 'E2E_TESTEXPR',
            description: 'Specify the --filter flag for UI E2E tests if necessary',
            defaultValue: '*'
            )
        choice(
            name: 'PLATFORM',
            description: 'The OS to install the Tower instance on',
            choices: ['rhel-7.6-x86_64', 'rhel-7.5-x86_64', 'rhel-7.4-x86_64',
                      'rhel-8.0-x86_64', 'ol-7.6-x86_64', 'centos-7.latest-x86_64',
                      'ubuntu-16.04-x86_64', 'ubuntu-14.04-x86_64']
        )
        choice(
            name: 'ANSIBLE_NIGHTLY_BRANCH',
            description: 'The Ansible version to install the Tower instance with',
            choices: ['devel', 'stable-2.8', 'stable-2.7', 'stable-2.6', 'stable-2.5', 'stable-2.4', 'stable-2.3']
        )
        string(
            name: 'SLACK_USERNAME',
            description: """\
            Send slack DM on completion. Use space separate list to sent to multiple people, for example: @johill @elyezer.
            The message sent will follow the parrot code: party_parrot (green, pipeline succeed and if tests were run everthing is passing), confusedparrot (yellow, tests were run and had failures) and sad_parrot (red, something went wrong with the pipeline).
            """,
            defaultValue: '#jenkins'
        )
        booleanParam(
            name: 'TEARDOWN_INSTANCE_ON_SUCCESS',
            description: """\
            Will teardown the Tower instance if the pipeline succeeds.
            This will only happen when RUN_TESTS and/or RUN_E2E are selected.
            Note: the EC2 instance that runs pytest is cleaned up immediately after yolo completes.
            """,
            defaultValue: true
        )
        string(
            name: 'COMMENTS',
            description: 'Custom message summarizing the purpose of this yolo job for the Slack Message',
            defaultValue: 'yolo'
        )
    }

    options {
        timestamps()
        buildDiscarder(logRotator(daysToKeepStr: '30'))
        timeout(time: 18, unit: 'HOURS')
    }

    stages {
        stage('Build Information') {
            steps {
                script {
                    if (params.TOWER_BRANCH == 'devel' && params.TOWER_PACKAGING_BRANCH == 'devel') {
                        NIGHTLY_REPO_DIR = 'devel'
                    } else {
                        NIGHTLY_REPO_DIR = "tower_${params.TOWER_BRANCH}_packaging_${params.TOWER_PACKAGING_BRANCH}"
                    }

                    if (params.PLATFORM == 'rhel-8.0-x86_64') {
                        target_dist = 'epel-8-x86_64'
                        mock_cfg = 'rhel-8-x86_64'
                    } else {
                        target_dist = 'epel-7-x86_64'
                        mock_cfg = 'rhel-7-x86_64'
                    }
                }
            }
        }

        stage('Build Tower and deploy test-runner') {
            failFast true
            parallel {
                stage('Build Installer') {
                    when {
                        expression {
                            return params.BUILD_INSTALLER_AND_PACKAGE
                        }
                    }

                    steps {
                        build(
                            job: 'Build_Tower_TAR',
                            parameters: [
                                string(
                                    name: 'TOWER_PACKAGING_REPO',
                                    value: "git@github.com:${params.TOWER_PACKAGING_FORK}/tower-packaging.git"
                                ),
                                string(
                                    name: 'TOWER_PACKAGING_BRANCH',
                                    value: "origin/${params.TOWER_PACKAGING_BRANCH}"
                                ),
                                string(
                                    name: 'TOWER_REPO',
                                    value: "git@github.com:${params.TOWER_FORK}/${params.PRODUCT}.git"
                                ),
                                string(
                                    name: 'TOWER_BRANCH',
                                    value: "origin/${params.TOWER_BRANCH}"
                                ),
                                string(
                                    name: 'NIGHTLY_REPO_DIR',
                                    value: NIGHTLY_REPO_DIR
                                )
                            ]
                        )
                    }
                }

                stage('Build Package') {
                    when {
                        expression {
                            return params.BUILD_INSTALLER_AND_PACKAGE
                        }
                    }

                    steps {
                        script {
                            if ( params.PLATFORM.contains('ubuntu') ) {
                                PACKAGE_JOB_NAME = 'Build_Tower_DEB'
                            } else {
                                PACKAGE_JOB_NAME = 'Build_Tower_RPM'
                            }

                            build(
                                job: PACKAGE_JOB_NAME,
                                parameters: [
                                    string(
                                        name: 'TOWER_PACKAGING_REPO',
                                        value: "git@github.com:${params.TOWER_PACKAGING_FORK}/tower-packaging.git"
                                    ),
                                    string(
                                        name: 'TOWER_PACKAGING_BRANCH',
                                        value: "origin/${params.TOWER_PACKAGING_BRANCH}"
                                    ),
                                    string(
                                        name: 'TOWER_REPO',
                                        value: "git@github.com:${params.TOWER_FORK}/${params.PRODUCT}.git"
                                    ),
                                    string(
                                        name: 'TOWER_BRANCH',
                                        value: "origin/${params.TOWER_BRANCH}"
                                    ),
                                    string(
                                        name: 'NIGHTLY_REPO_DIR',
                                        value: NIGHTLY_REPO_DIR
                                    ),
                                    string(
                                        name: 'TARGET_DIST',
                                        value: target_dist
                                    ),
                                    string(
                                        name: 'MOCK_CFG',
                                        value: mock_cfg
                                    ),
                                    booleanParam(
                                        name: 'TRIGGER',
                                        value: false
                                    )
                                ]
                            )
                        }
                    }
                }

                stage('Deploy test-runner node') {
                    when {
                        expression {
                            return params.RUN_INSTALLER
                        }
                    }

                    steps {
                        checkout([
                            $class: 'GitSCM',
                            branches: [[name: "*/${params.TOWER_QA_BRANCH}" ]],
                            userRemoteConfigs: [
                                [
                                    credentialsId: 'd2d4d16b-dc9a-461b-bceb-601f9515c98a',
                                    url: "git@github.com:${params.TOWER_QA_FORK}/tower-qa.git"
                                ]
                            ]
                        ])

                        script {
                            if (params.RUNNER_FORK != '' && params.RUNNER_BRANCH != '') {
                                AWX_ANSIBLE_RUNNER_URL = "https://github.com/${params.RUNNER_FORK}/ansible-runner.git@${params.RUNNER_BRANCH}"
                            } else {
                                AWX_ANSIBLE_RUNNER_URL = ''
                            }
                        }

                        withCredentials([file(credentialsId: '171764d8-e57c-4332-bff8-453670d0d99f', variable: 'PUBLIC_KEY'),
                                        file(credentialsId: 'abcd0260-fb83-404e-860f-f9697911a0bc', variable: 'VAULT_FILE'),
                                        file(credentialsId: '86ed99e9-dad9-49e9-b0db-9257fb563bad', variable: 'JSON_KEY_FILE'),
                                        string(credentialsId: 'aws_access_key', variable: 'AWS_ACCESS_KEY'),
                                        string(credentialsId: 'aws_secret_key', variable: 'AWS_SECRET_KEY'),
                                        string(credentialsId: 'awx_admin_password', variable: 'AWX_ADMIN_PASSWORD')]) {
                            withEnv(["AWS_SECRET_KEY=${AWS_SECRET_KEY}",
                                     "AWS_ACCESS_KEY=${AWS_ACCESS_KEY}",
                                     "AWX_ADMIN_PASSWORD=${AWX_ADMIN_PASSWORD}",
                                     "AWX_ANSIBLE_RUNNER_URL=${AWX_ANSIBLE_RUNNER_URL}",
                                     "SCENARIO=${SCENARIO}",
                                     "PLATFORM=${PLATFORM}",
                                     "ANSIBLE_VERSION=${ANSIBLE_NIGHTLY_BRANCH}",
                                     "DEPLOYMENT_NAME=yolo-build-${env.BUILD_ID}",
                                     "AW_REPO_URL=http://nightlies.testing.ansible.com/ansible-tower_nightlies_m8u16fz56qr6q7/${NIGHTLY_REPO_DIR}"]) {
                                sshagent(credentials : ['d2d4d16b-dc9a-461b-bceb-601f9515c98a']) {
                                    sh 'mkdir -p ~/.ssh && cp ${PUBLIC_KEY} ~/.ssh/id_rsa.pub'
                                    sh 'cp ${JSON_KEY_FILE} json_key_file'
                                    sh 'ansible-vault decrypt --vault-password-file="${VAULT_FILE}" config/credentials.vault --output=config/credentials.yml'
                                    sh 'ansible-vault decrypt --vault-password-file="${VAULT_FILE}" config/credentials-pkcs8.vault --output=config/credentials-pkcs8.yml || true'

                                    // Generate variable file for test runner
                                    sh 'SCENARIO=test_runner ./tools/jenkins/scripts/generate_vars.sh'

                                    // Generate variable file for tower deployment
                                    sh './tools/jenkins/scripts/generate_vars.sh'

                                    sh 'ansible-playbook -v -i playbooks/inventory -e @playbooks/test_runner_vars.yml playbooks/deploy-test-runner.yml'

                                    // Archive test runner inventory file and show it to user so they can optionally shell in
                                    sh 'mkdir -p artifacts'
                                    sh 'cat playbooks/inventory.test_runner | tee artifacts/inventory.test_runner'
                                    sh 'grep -A 1 test-runner playbooks/inventory.test_runner | tail -n 1 | cut -d" " -f1 > artifacts/test_runner_host'

                                    sh "ansible test-runner -i playbooks/inventory.test_runner -m git -a 'repo=git@github.com:${params.TOWER_QA_FORK}/tower-qa version=${params.TOWER_QA_BRANCH} dest=tower-qa ssh_opts=\"-o StrictHostKeyChecking=no\" force=yes'"
                                }
                            }
                        }

                        script {
                            TEST_RUNNER_HOST = readFile('artifacts/test_runner_host').trim()
                            SSH_OPTS = '-o ForwardAgent=yes -o StrictHostKeyChecking=no'
                        }
                    }
                }
            }
        }

        stage('Install Tower') {
            when {
                expression {
                    return params.RUN_INSTALLER
                }
            }

            steps {
                sshagent(credentials : ['d2d4d16b-dc9a-461b-bceb-601f9515c98a']) {
                    sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/install.sh'"
                    sh 'ansible-playbook -v -i playbooks/inventory.test_runner playbooks/test_runner/run_fetch_artifacts.yml'
                }
            }
        }

        stage('Run Integration Tests') {
            when {
                expression {
                    return params.RUN_TESTS
                }
            }

            steps {
                sshagent(credentials : ['d2d4d16b-dc9a-461b-bceb-601f9515c98a']) {
                    sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && TESTEXPR=\"${params.TESTEXPR}\" TOWERKIT_BRANCH=\"${params.TOWERKIT_BRANCH}\" ./tools/jenkins/scripts/test.sh'"
                    sh 'ansible-playbook -v -i playbooks/inventory.test_runner playbooks/test_runner/run_fetch_artifacts_test.yml'
                    junit 'artifacts/results.xml'
                }
            }

        }

        stage('Run E2E Tests') {
            when {
                expression {
                    return params.RUN_E2E
                }
            }

            steps {
                script {
                    AWX_E2E_URL = readFile('artifacts/tower_url').trim()
                    
                    if  (params.RETRY_FAILED_TESTS) {
                        env.RETRY_E2E_STAGE_COUNT = "2"
                        env.E2E_RETRIES = "2"
                    }
                    else { 
                        env.RETRY_E2E_COUNT = "0"
                        env.E2E_RETRIES = "0"
                    }                

                    retry(env.RETRY_E2E_STAGE_COUNT) {
                        build(
                            job: 'Test_Tower_E2E',
                            parameters: [
                                string(
                                    name: 'E2E_URL',
                                    value: "${AWX_E2E_URL}"
                                ),
                                string(
                                    name: 'DEPLOYMENT_TYPE',
                                    value: "${params.PRODUCT}"
                                ),
                                string(
                                    name: 'E2E_FORK',
                                    value: "${params.TOWER_FORK}"
                                ),
                                string(
                                    name: 'E2E_BRANCH',
                                    value: "${params.TOWER_BRANCH}"
                                ),
                                string(
                                    name: 'E2E_TEST_SELECTION',
                                    value: "${params.E2E_TESTEXPR}"
                                ),
                                string(
                                    name: 'E2E_RETRIES',
                                    value: "${env.E2E_RETRIES}"
                                )
                            ]
                        )
                    }
                }
            }
        }
        stage('Collect SOS reports from Tower instances') {
            when {
                expression {
                    return (params.RUN_INSTALLER || params.RUN_TESTS || params.RUN_E2E)
                }
            }

            steps {
                sshagent(credentials : ['d2d4d16b-dc9a-461b-bceb-601f9515c98a']) {
                    sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/collect.sh'"
                    sh 'ansible-playbook -v -i playbooks/inventory.test_runner playbooks/test_runner/run_fetch_artifacts_tower.yml'
                }
            }
        }
    }
    post {
        always {
            archiveArtifacts allowEmptyArchive: true, artifacts: 'artifacts/*'
        }
        success {
            slackSend(
                botUser: false,
                color: "good",
                teamDomain: "ansible",
                channel: "${SLACK_USERNAME}",
                message: genSlackMessage('party_parrot')
            )

            script {
                if (params.TEARDOWN_INSTANCE_ON_SUCCESS && (params.RUN_TESTS || params.RUN_E2E) && params.TESTEXPR != 'test') {
                    sshagent(credentials : ['d2d4d16b-dc9a-461b-bceb-601f9515c98a']) {
                        sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/cleanup.sh'"
                    }
                }
            }
        }
        failure {
            slackSend(
                botUser: false,
                color: "danger",
                teamDomain: "ansible",
                channel: "${SLACK_USERNAME}",
                message: genSlackMessage('sad_parrot')
            )
        }
        unstable {
            slackSend(
                botUser: false,
                color: "warning",
                teamDomain: "ansible",
                channel: "${SLACK_USERNAME}",
                message: genSlackMessage('confusedparrot')
            )
        }
        cleanup {
            script {
                if (params.TESTEXPR == 'test' && params.SCENARIO == 'standalone'  && params.RUN_TESTS) {
                    sshagent(credentials : ['d2d4d16b-dc9a-461b-bceb-601f9515c98a']) {
                        sh "ssh ${SSH_OPTS} ec2-user@${TEST_RUNNER_HOST} 'cd tower-qa && ./tools/jenkins/scripts/cleanup.sh'"
                    }
                }
            }

            sshagent(credentials : ['d2d4d16b-dc9a-461b-bceb-601f9515c98a']) {
                sh 'ansible-playbook -v -i playbooks/inventory -e @playbooks/test_runner_vars.yml playbooks/reap-tower-ec2.yml'
            }
        }
    }
}

def genSlackMessage (parrot) {
    message = "<${env.RUN_DISPLAY_URL}|yolo #${env.BUILD_ID}> took ${currentBuild.durationString.replace(' and counting', '')} and is :${parrot}:\n"

    if (fileExists('artifacts/tower_url')) {
        message += "Instance URL - ${readFile('artifacts/tower_url').trim()}\n"
    } else {
        message += 'Instance URL - N/A\n'
    }

    message += """\
        Platform - ${params.PLATFORM}
        Product - ${params.PRODUCT} - ${params.TOWER_FORK}/${params.TOWER_BRANCH}
        Scenario - ${params.SCENARIO}
        Tower-Packaging - ${params.TOWER_PACKAGING_FORK}/${params.TOWER_PACKAGING_BRANCH}
        Tower-QA - ${params.TOWER_QA_FORK}/${params.TOWER_QA_BRANCH}
        Ansible Version - ${params.ANSIBLE_NIGHTLY_BRANCH}
    """.stripIndent()

    if (params.RUN_TESTS) {
        message += "Test Expression - ${params.TESTEXPR}\n"
    }
    if (params.RUN_E2E) {
        message += "E2E Test Expression - ${params.E2E_TESTEXPR}\n"
    }

    message += "Comments - ${params.COMMENTS}\n"
    return message
}
