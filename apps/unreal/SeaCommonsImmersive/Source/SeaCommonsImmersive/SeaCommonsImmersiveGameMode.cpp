#include "SeaCommonsImmersiveGameMode.h"

#include "CineCameraActor.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "SeaCommonsSceneController.h"

void ASeaCommonsImmersiveGameMode::BeginPlay()
{
    Super::BeginPlay();

    if (UWorld* World = GetWorld())
    {
        World->SpawnActor<ASeaCommonsSceneController>();

        APlayerController* PlayerController =
            UGameplayStatics::GetPlayerController(World, 0);
        if (PlayerController)
        {
            for (TActorIterator<ACineCameraActor> It(World); It; ++It)
            {
                PlayerController->SetViewTarget(*It);
                break;
            }
        }
    }
}
