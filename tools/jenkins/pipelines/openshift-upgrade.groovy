pipeline {

    agent { label 'jenkins-jnlp-agent' }

    parameters {
        choice(
            name: 'TOWER_VERSION_TO_UPGRADE_FROM',
            description: 'Tower version to upgrade from ?',
            choices: ['3.5.1', '3.5.0',
                      '3.4.4', '3.4.3', '3.4.2', '3.4.1', '3.4.0',
                      '3.3.6', '3.3.5', '3.3.4', '3.3.3', '3.3.2', '3.3.1', '3.3.0']
        )
        choice(
            name: 'TOWER_VERSION_TO_UPGRADE_TO',
            description: 'Tower version to upgrade to ?',
            choices: ['devel', '3.5.2', '3.5.1', '3.5.0',
                      '3.4.5', '3.4.4', '3.4.3', '3.4.2', '3.4.1', '3.4.0',
                      '3.3.7', '3.3.6', '3.3.5', '3.3.4', '3.3.3', '3.3.2', '3.3.1', '3.3.0']
        )
        string(
            name: 'TOWERQA_BRANCH',
            description: 'ansible/tower-qa branch to use (Empty will do the right thing)',
            defaultValue: ''
        )
        string(
            name: 'TOWER_CONTAINER_IMAGE_TO_UPGRADE_FROM',
            description: 'Override the URL from which the Tower container image to upgrade from will be pulled from. (Empty will pull the proper one based on TOWER_VERSION_TO_UPGRADE_FROM)',
            defaultValue: ''
        )
        string(
            name: 'MESSAGING_CONTAINER_IMAGE_TO_UPGRADE_FROM',
            description: 'Override the URL from which the Tower Messaging container image to upgrade from will be pulled from. (Empty will pull the proper one based on TOWER_VERSION_TO_UPGRADE_FROM)',
            defaultValue: ''
        )
        string(
            name: 'MEMCACHED_CONTAINER_IMAGE_TO_UPGRADE_FROM',
            description: 'Override the URL from which the Tower Memcached container image to upgrade from will be pulled from. (Empty will pull the proper one based on TOWER_VERSION_TO_UPGRADE_FROM)',
            defaultValue: ''
        )
        string(
            name: 'TOWER_CONTAINER_IMAGE_TO_UPGRADE_TO',
            description: 'Override the URL from which the Tower container image to upgrade to will be pulled from. (Empty will pull the proper one based on TOWER_VERSION_TO_UPGRADE_TO)',
            defaultValue: ''
        )
        string(
            name: 'MESSAGING_CONTAINER_IMAGE_TO_UPGRADE_TO',
            description: 'Override the URL from which the Tower Messaging container image to upgrade to will be pulled from. (Empty will pull the proper one based on TOWER_VERSION_TO_UPGRADE_TO)',
            defaultValue: ''
        )
        string(
            name: 'MEMCACHED_CONTAINER_IMAGE_TO_UPGRADE_TO',
            description: 'Override the URL from which the Tower Memcached container image to upgrade to will be pulled from. (Empty will pull the proper one based on TOWER_VERSION_TO_UPGRADE_TO)',
            defaultValue: ''
        )
        choice(
            name: 'CLEAN_DEPLOYMENT_AFTER_JOB_RUN',
            description: 'Should the deployment be removed after job is run ?',
            choices: ['yes', 'no']
        )
    }

    options {
        timestamps()
        timeout(time: 2, unit: 'HOURS')
        buildDiscarder(logRotator(daysToKeepStr: '30'))
    }

    stages {

        stage('Build Information') {
            steps {
                echo """Tower Version under test: ${params.TOWER_VERSION}
ansible/tower-qa branch: ${params.TOWERQA_BRANCH}
Tower Container Image: ${params.TOWER_CONTAINER_IMAGE}
Tower Messaging Container Image: ${params.MESSAGING_CONTAINER_IMAGE}
Tower Memcached Container Image: ${params.MEMCACHED_CONTAINER_IMAGE}"""
            }
        }

        stage('Checkout tower-qa') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: "*/release_${params.TOWER_VERSION_TO_UPGRADE_FROM}" ]],
                    userRemoteConfigs: [
                        [
                            credentialsId: 'd2d4d16b-dc9a-461b-bceb-601f9515c98a',
                            url: 'git@github.com:ansible/tower-qa.git'
                        ]
                    ]
                ])
            }
        }

        stage('Prepare Environment') {
            steps {
                withCredentials([file(credentialsId: 'abcd0260-fb83-404e-860f-f9697911a0bc', variable: 'VAULT_FILE'),
                                 string(credentialsId: 'awx_admin_password', variable: 'AWX_ADMIN_PASSWORD')]) {
                    withEnv(["SCENARIO=openshift",
                             "OPENSHIFT_PASS=${AWX_ADMIN_PASSWORD}",
                             "AWX_ADMIN_PASSWORD=${AWX_ADMIN_PASSWORD}",
                             "TOWER_VERSION=${params.TOWER_VERSION_TO_UPGRADE_FROM}"]) {
                        sh 'ansible-vault decrypt --vault-password-file="${VAULT_FILE}" config/credentials.vault --output=config/credentials.yml'
                        sh './tools/jenkins/scripts/generate_vars.sh'
                    }
                }
            }
        }

        stage ('Install') {
            steps {
                withCredentials([string(credentialsId: 'awx_admin_password', variable: 'AWX_ADMIN_PASSWORD')]) {
                    withEnv(["OPENSHIFT_PASS=${AWX_ADMIN_PASSWORD}",
                             "TOWER_CONTAINER_IMAGE=${params.TOWER_CONTAINER_IMAGE_TO_UPGRADE_FROM}",
                             "MESSAGING_CONTAINER_IMAGE=${params.MESSAGING_CONTAINER_IMAGE_TO_UPGRADE_FROM}",
                             "MEMCACHED_CONTAINER_IMAGE=${params.MEMCACHED_CONTAINER_IMAGE_TO_UPGRADE_FROM}",
                             "ANSIBLE_FORCE_COLOR=true"]) {
                        sh './tools/jenkins/scripts/openshift_install.sh'
                    }
                }

                script {
                    // artifacts/openshift_project gets written by tower-qa/tools/jenkins/scripts/openshift_install.sh
                    OPENSHIFT_PROJECT = readFile('artifacts/openshift_project').trim()
                }
            }
        }

        stage ('Load data') {
            steps {
                sshagent(credentials : ['d2d4d16b-dc9a-461b-bceb-601f9515c98a']) {
                    sh './tools/jenkins/scripts/load.sh'
                }
            }
        }

        stage('Checkout newer tower-qa') {
            steps {
                script {
                    if (params.TOWERQA_BRANCH == '') {
                        if (params.TOWER_VERSION == 'devel') {
                            branch_name = 'devel'
                        } else {
                            branch_name = "release_${params.TOWER_VERSION_TO_UPGRADE_TO}"
                        }
                    } else {
                        branch_name = params.TOWERQA_BRANCH
                    }
                }
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: "*/${branch_name}" ]],
                    userRemoteConfigs: [
                        [
                            credentialsId: 'd2d4d16b-dc9a-461b-bceb-601f9515c98a',
                            url: 'git@github.com:ansible/tower-qa.git'
                        ]
                    ]
                ])
            }
        }

        stage ('Upgrade') {
            steps {
                withCredentials([string(credentialsId: 'awx_admin_password', variable: 'AWX_ADMIN_PASSWORD')]) {
                    withEnv(["OPENSHIFT_PASS=${AWX_ADMIN_PASSWORD}",
                             "OPENSHIFT_PROJECT=${OPENSHIFT_PROJECT}",
                             "AWX_ADMIN_PASSWORD=${AWX_ADMIN_PASSWORD}",
                             "TOWER_CONTAINER_IMAGE=${params.TOWER_CONTAINER_IMAGE_TO_UPGRADE_TO}",
                             "MESSAGING_CONTAINER_IMAGE=${params.MESSAGING_CONTAINER_IMAGE_TO_UPGRADE_TO}",
                             "MEMCACHED_CONTAINER_IMAGE=${params.MEMCACHED_CONTAINER_IMAGE_TO_UPGRADE_TO}",
                             "ANSIBLE_FORCE_COLOR=true",
                             "SCENARIO=openshift",
                             "AWX_UPGRADE=true",
                             "TOWER_VERSION=${params.TOWER_VERSION_TO_UPGRADE_TO}"]) {
                        sh './tools/jenkins/scripts/generate_vars.sh'
                        sh './tools/jenkins/scripts/openshift_install.sh'
                    }
                }
            }
        }

        stage ('Verify data integrity') {
            steps {
                sshagent(credentials : ['d2d4d16b-dc9a-461b-bceb-601f9515c98a']) {
                    sh './tools/jenkins/scripts/verify.sh'
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts allowEmptyArchive: true, artifacts: 'artifacts/*'
        }
        cleanup {
            script {
                if (params.CLEAN_DEPLOYMENT_AFTER_JOB_RUN == 'yes') {
                    withCredentials([string(credentialsId: 'awx_admin_password', variable: 'AWX_ADMIN_PASSWORD')]) {
                        withEnv(["OPENSHIFT_PASS=${AWX_ADMIN_PASSWORD}",
                                 "OPENSHIFT_PROJECT=${OPENSHIFT_PROJECT}"]) {
                            sh './tools/jenkins/scripts/openshift_cleanup.sh'
                        }
                    }
                }
            }
        }
    }
}
