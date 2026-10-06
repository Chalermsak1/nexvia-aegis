from aegis.v3.agent import AegisAgentV3


def main():
    agent = AegisAgentV3()
    agent.run_episode(seed=42)


if __name__ == "__main__":
    main()
